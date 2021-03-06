"""Tinymud launcher."""

import asyncio
import argparse
from enum import Enum
from multiprocessing import Process
from pathlib import Path
import signal
import sys
from typing import Any

from loguru import logger


class FileSet(Enum):
    """Set of game, Tinymud and dependency sources.

    GAME includes current game source code, CORE that and core Tinymud sources,
    while ALL includes everything (including dependencies).
    """
    NONE = 'none'
    GAME = 'game'
    CORE = 'core'

    def __str__(self) -> str:
        return self.value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tinymud launcher")
    parser.add_argument('game', help="Path to Tinymud game")
    parser.add_argument('--db', help="Connect to this PostgreSQL database.")
    parser.add_argument('--dev-db', action='store_true',
        help="Launch an empty development database with Docker.")
    parser.add_argument('--watch', type=FileSet, choices=list(FileSet),
        help="Watch file set for changes and reload it when they occur.")
    parser.add_argument('--test-login', action='store_true',
        help="Disable authentication (!!!) and restrict connections to localhost")
    parser.add_argument('--enable-profiler', action='store_true',
        help="Enables profiling")
    parser.add_argument('--update-schema', action='store_true',
        help="Generate and update table schemas interactively.")
    parser.add_argument('--prod', action='store_true', help="Enables production mode.")
    parser.add_argument('--save-interval', default=30, type=float,
        help="Sets the database commit interval (in seconds).")
    parser.add_argument('--host', default='localhost', help="Application host.")
    parser.add_argument('--port', default=8080, help="Application port.")

    return parser.parse_args()


def launch_dev_db() -> Any:
    """Launcher empty database in Postgres."""
    import docker
    client = docker.from_env()
    return client.containers.run('postgres:13-alpine', detach=True, remove=True, ports={'5432': ('127.0.0.1', 23123)},
        environment={'POSTGRES_DB': 'tinymud', 'POSTGRES_PASSWORD': 'localdevonly'})


def import_for_fork(reloadable: FileSet) -> None:
    """Import modules that don't need to be reloadable.

    This may speed up live reloads, but obviously prevents reloading some
    modules.
    """
    import asyncpg  # noqa
    pass  # TODO implement more :)


def watch_files(reloadable: FileSet, game_path: Path) -> Any:
    if reloadable == FileSet.NONE:
        return None  # Nothing to watch
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEvent, FileSystemEventHandler

    # Reloads everything whenever anything changes
    class ReloadingEventHandler(FileSystemEventHandler):
        def on_any_event(self, event: FileSystemEvent) -> None:
            print("Live-reloading...")
            stop_tinymud(True)
            # Main will restart subprocess, because no SIGINT was received
    handler = ReloadingEventHandler()

    observer = Observer()
    if reloadable == FileSet.GAME:
        observer.schedule(handler, game_path, recursive=True)
    if reloadable == FileSet.CORE:
        observer.schedule(handler, game_path, recursive=True)
        observer.schedule(handler, 'tinymud', recursive=True)
    observer.start()
    return observer


_db_url: str  # Database URL for subprocess usage
_dev_db = None  # Development database container (if present)
_game_path: Path  # Game directory
_prod_mode: bool
_update_schema: bool
_save_interval: int
_host: str
_port: int
_test_login: bool
_enable_yappi: bool


_mud_proc: Process  # Currently running subprocess
_restart_flag: bool = True  # True if starting for first time or restarting
_observer = None  # Observer for --watch, if watching any files


def _mudproc_entrypoint() -> None:
    if _update_schema:  # Need interactive console
        sys.stdin = open(0)

    if _observer:  # Let launcher process handle restarting
        _observer.stop()

    if _enable_yappi:
        import yappi
        yappi.start()

    def do_exit() -> None:
        if _enable_yappi:
            with open('profile.txt', 'w') as out:
                yappi.get_func_stats().print_all(out=out)

        sys.exit()

    # Replace quit-signal handlers with sys.exit()
    # While we do have handle to current process, it cannot be terminate()d
    # outside of the process fork()ing to it (i.e. our parent, launcher)
    signal.signal(signal.SIGINT, lambda signal, handler: do_exit())
    signal.signal(signal.SIGTERM, lambda signal, handler: do_exit())

    import tinymud
    loop = asyncio.get_event_loop()
    loop.create_task(tinymud.start(db_url=_db_url, game_path=_game_path,
        prod_mode=_prod_mode, update_schema=_update_schema, save_interval=_save_interval,
        host=_host, port=_port, test_login=_test_login))
    loop.run_forever()


def launch_tinymud() -> None:
    global _mud_proc
    _mud_proc = Process(target=_mudproc_entrypoint)
    _mud_proc.start()
    _mud_proc.join()


def stop_tinymud(restart: bool = False) -> None:
    if restart:
        global _restart_flag
        _restart_flag = True  # Don't quit, but restart instead
    _mud_proc.terminate()  # SIGTERM, graceful exit


if __name__ == '__main__':
    args = parse_args()

    if args.dev_db:  # Launch development database and connect to it
        logger.info("Using Docker to start development database")
        _dev_db = launch_dev_db()
        _db_url = 'postgres://postgres:localdevonly@localhost:23123/tinymud'
    else:  # Connect to externally managed (prod?) PostgreSQL
        # NOTE: Don't ever log db_url, it contains the password!
        _db_url = args.db

    # Add signal handlers for exiting
    signal.signal(signal.SIGINT, lambda signal, handler: stop_tinymud())
    signal.signal(signal.SIGTERM, lambda signal, handler: stop_tinymud())

    # Preload files that don't need live-reload
    if args.watch:
        reloadable = args.watch
    else:
        reloadable = FileSet.NONE
    import_for_fork(reloadable)

    # Convert game path to absolute to avoid "fun" if/when workdir changes
    _game_path = Path(args.game).absolute()

    # Make rest of arguments available for forking
    _prod_mode = args.prod
    _update_schema = args.update_schema
    _save_interval = args.save_interval
    _host = args.host
    _port = args.port
    _test_login = args.test_login
    _enable_yappi = args.enable_profiler
    if _test_login:  # Force to localhost for security reasons
        _host = 'localhost'

    # Watch for file changes to trigger reloads
    _observer = watch_files(reloadable, _game_path)

    # Launch app unless we received SIGINT to stop
    while _restart_flag:
        _restart_flag = False
        launch_tinymud()

    # Clean up once _quit_received is set
    if _dev_db:  # Stop development DB if it exists
        logger.info("Killing development database")
        _dev_db.kill()
