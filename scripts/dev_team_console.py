#!/usr/bin/env python3
from __future__ import annotations

import queue
import shlex
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import count
from typing import Callable


ROLE_TL = "TL"
ROLE_ARCH = "Architect"
ROLE_DEV = "SeniorDev"
ROLE_QA = "QA"
ROLE_SEC = "DevSecOps"

ALL_ROLES = (ROLE_TL, ROLE_ARCH, ROLE_DEV, ROLE_QA, ROLE_SEC)


@dataclass
class Event:
    event_id: int
    timestamp: str
    kind: str
    actor: str
    message: str


@dataclass
class Task:
    task_id: int
    sender: str
    recipient: str
    message: str


class EventBus:
    def __init__(self) -> None:
        self._events: list[Event] = []
        self._events_lock = threading.Lock()
        self._subscribers: list[queue.Queue[Event]] = []
        self._subscribers_lock = threading.Lock()
        self._event_ids = count(1)

    def publish(self, kind: str, actor: str, message: str) -> Event:
        event = Event(
            event_id=next(self._event_ids),
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            kind=kind,
            actor=actor,
            message=message,
        )
        with self._events_lock:
            self._events.append(event)
        with self._subscribers_lock:
            for subscriber in self._subscribers:
                subscriber.put(event)
        return event

    def tail(self, limit: int = 20) -> list[Event]:
        with self._events_lock:
            return self._events[-limit:]

    def subscribe(self) -> queue.Queue[Event]:
        subscriber: queue.Queue[Event] = queue.Queue()
        with self._subscribers_lock:
            self._subscribers.append(subscriber)
        return subscriber


class Orchestrator:
    def __init__(self, bus: EventBus) -> None:
        self.bus = bus
        self._task_ids = count(1)
        self._task_queues = {role: queue.Queue() for role in ALL_ROLES}
        self._workers: list[threading.Thread] = []
        self._stop = threading.Event()

    def start(self) -> None:
        for role in ALL_ROLES:
            worker = threading.Thread(target=self._worker_loop, args=(role,), daemon=True)
            self._workers.append(worker)
            worker.start()
        self.bus.publish("system", "orchestrator", "Equipo multiagente iniciado.")

    def stop(self) -> None:
        self._stop.set()
        for role, task_queue in self._task_queues.items():
            task_queue.put(Task(0, "system", role, "__stop__"))

    def assign(self, sender: str, recipient: str, message: str) -> None:
        if recipient not in self._task_queues:
            self.bus.publish("error", "orchestrator", f"Rol desconocido: {recipient}")
            return
        task = Task(next(self._task_ids), sender, recipient, message)
        self.bus.publish("task", sender, f"->{recipient} #{task.task_id}: {message}")
        self._task_queues[recipient].put(task)

    def kickoff(self, objective: str) -> None:
        self.bus.publish("system", "orchestrator", f"Kickoff de proyecto: {objective}")
        self.assign("user", ROLE_TL, objective)

    def _worker_loop(self, role: str) -> None:
        while not self._stop.is_set():
            task: Task = self._task_queues[role].get()
            if task.message == "__stop__":
                return
            response = self._build_response(role, task)
            # Simulate thinking time to make interactions observable.
            time.sleep(0.35)
            self.bus.publish("reply", role, f"#{task.task_id} para {task.sender}: {response}")
            self._fan_out(role, task)

    def _build_response(self, role: str, task: Task) -> str:
        msg = task.message.strip()
        if role == ROLE_TL:
            return (
                f"Recibido. Descompongo el objetivo en arquitectura, implementacion, QA y DevSecOps: '{msg}'."
            )
        if role == ROLE_ARCH:
            return (
                "Propongo arquitectura event-driven: EventBus + Orchestrator + agentes por rol + consola interactiva."
            )
        if role == ROLE_DEV:
            return (
                "Implementare comandos interactivos: run, ask, kickoff, logs, stream, status; con captura de stdout/stderr."
            )
        if role == ROLE_QA:
            return (
                "Defino smoke checks: inicio/parada de agentes, registro de eventos y ejecucion de comandos con salida capturada."
            )
        if role == ROLE_SEC:
            return (
                "Incluire controles DevSecOps: no ejecutar comandos vacios, timeout configurable y trazabilidad de auditoria."
            )
        return "Tarea recibida."

    def _fan_out(self, role: str, task: Task) -> None:
        if role != ROLE_TL:
            return
        objective = task.message.strip()
        self.assign(ROLE_TL, ROLE_ARCH, f"Disena arquitectura para: {objective}")
        self.assign(ROLE_TL, ROLE_DEV, f"Implementa flujo base para: {objective}")
        self.assign(ROLE_TL, ROLE_QA, f"Define validacion para: {objective}")
        self.assign(ROLE_TL, ROLE_SEC, f"Define controles y hardening para: {objective}")


class CommandRunner:
    def __init__(self, bus: EventBus) -> None:
        self.bus = bus

    def run(self, command: str, timeout: int = 180) -> None:
        command = command.strip()
        if not command:
            self.bus.publish("error", "terminal", "Comando vacio.")
            return

        self.bus.publish("terminal.input", "terminal", command)
        try:
            completed = subprocess.run(
                command,
                shell=True,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            self.bus.publish("terminal.error", "terminal", f"Timeout tras {timeout}s")
            return

        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()

        if stdout:
            for line in stdout.splitlines():
                self.bus.publish("terminal.output", "stdout", line)
        if stderr:
            for line in stderr.splitlines():
                self.bus.publish("terminal.output", "stderr", line)

        self.bus.publish("terminal.exit", "terminal", f"exit_code={completed.returncode}")


class StreamPrinter:
    def __init__(self, bus: EventBus) -> None:
        self.bus = bus
        self._stream = False
        self._stop = threading.Event()
        self._queue = bus.subscribe()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def set_enabled(self, enabled: bool) -> None:
        self._stream = enabled

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                event = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if self._stream:
                print(format_event(event))


def format_event(event: Event) -> str:
    return f"[{event.timestamp}] ({event.kind}) {event.actor}: {event.message}"


def print_help() -> None:
    print("Comandos disponibles:")
    print("  help")
    print("  stream on|off")
    print("  logs [n]")
    print("  wait [segundos]")
    print("  roles")
    print("  status")
    print("  ask <rol> <mensaje>")
    print("  kickoff <objetivo>")
    print("  run <comando-shell>")
    print("  exit")


def parse_input(raw: str) -> tuple[str, list[str]]:
    parts = shlex.split(raw)
    if not parts:
        return "", []
    return parts[0], parts[1:]


def main() -> None:
    bus = EventBus()
    orchestrator = Orchestrator(bus)
    runner = CommandRunner(bus)
    stream = StreamPrinter(bus)

    orchestrator.start()
    stream.set_enabled(True)

    bus.publish(
        "system",
        "console",
        "Consola interactiva lista. Escribe 'help' para ver comandos.",
    )

    role_aliases: dict[str, str] = {
        "tl": ROLE_TL,
        "architect": ROLE_ARCH,
        "arch": ROLE_ARCH,
        "seniordev": ROLE_DEV,
        "dev": ROLE_DEV,
        "qa": ROLE_QA,
        "devsecops": ROLE_SEC,
        "sec": ROLE_SEC,
    }

    try:
        while True:
            raw = input("> ").strip()
            command, args = parse_input(raw)

            if command == "":
                continue
            if command == "help":
                print_help()
                continue
            if command == "exit":
                break
            if command == "stream":
                if not args or args[0] not in {"on", "off"}:
                    print("Uso: stream on|off")
                    continue
                enabled = args[0] == "on"
                stream.set_enabled(enabled)
                bus.publish("system", "console", f"stream={'on' if enabled else 'off'}")
                continue
            if command == "logs":
                limit = 20
                if args:
                    try:
                        limit = max(1, int(args[0]))
                    except ValueError:
                        print("Uso: logs [n]")
                        continue
                for event in bus.tail(limit):
                    print(format_event(event))
                continue
            if command == "wait":
                seconds = 2.0
                if args:
                    try:
                        seconds = max(0.0, float(args[0]))
                    except ValueError:
                        print("Uso: wait [segundos]")
                        continue
                bus.publish("system", "console", f"Esperando {seconds:.1f}s para observar eventos...")
                time.sleep(seconds)
                continue
            if command == "roles":
                print("Roles disponibles:", ", ".join(ALL_ROLES))
                continue
            if command == "status":
                print("stream=", "on" if stream._stream else "off")
                print("agentes=", ", ".join(ALL_ROLES))
                continue
            if command == "ask":
                if len(args) < 2:
                    print("Uso: ask <rol> <mensaje>")
                    continue
                role_key = args[0].lower()
                message = " ".join(args[1:])
                role = role_aliases.get(role_key)
                if role is None:
                    print("Rol invalido. Usa: tl, architect, seniordev, qa, devsecops")
                    continue
                orchestrator.assign("user", role, message)
                continue
            if command == "kickoff":
                if not args:
                    print("Uso: kickoff <objetivo>")
                    continue
                orchestrator.kickoff(" ".join(args))
                continue
            if command == "run":
                if not args:
                    print("Uso: run <comando-shell>")
                    continue
                runner.run(" ".join(args))
                continue

            print("Comando no reconocido. Escribe 'help'.")
    except KeyboardInterrupt:
        print("\nInterrupcion recibida.")
    finally:
        stream.stop()
        orchestrator.stop()
        bus.publish("system", "console", "Consola cerrada.")


if __name__ == "__main__":
    main()
