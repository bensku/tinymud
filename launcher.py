"""Tinymud launcher."""

import asyncio
import argparse
from enum import Enum
from multiprocessing import Process
from pathlib import Path
import signal


class FileSet(Enum):
    """Set of game, Tinymud and dependency sources.

    GAME includes current game source code, CORE that and core Tinymud sources,
    while ALL includes everything (including dependencies).
    """
    NONE = 'none'
    GAME = 'game'
    CORE = 'core'

    def __str(self):
        return self.value


def parse_args():
    parser = argparse.ArgumentParser(description="Tinymud launcher")
    parser.add_argument('game', help="Path to Tinymud game")
    parser.add_argument('--db', help="Connect to this PostgreSQL database.")
    parser.add_argument('--dev-db', action='store_true',
        help="Launch an empty development database with Docker.")
    parser.add_argument('--watch', type=FileSet, choices=list(FileSet),
        help="Watch file set for changes and reload it when they occur.")

    return parser.parse_args()


def launch_dev_db():
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


def watch_files(reloadable: FileSet, game_path: str) -> None:
    if reloadable == FileSet.NONE:
        return  # Nothing to watch
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    # Reloads everything whenever anything changes
    class ReloadingEventHandler(FileSystemEventHandler):
        def on_any_event(self, event):
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


_db_url: str  # Database URL for subprocess usage
_dev_db = None  # Development database container (if present)
_game_path: Path  # Game directory
_mud_proc: Process  # Currently running subprocess
_restart_flag: bool = True  # True if starting for first time or restarting


def _mudproc_entrypoint():
    import tinymud
    asyncio.run(tinymud.start(_db_url, _game_path))


def launch_tinymud():
    global _mud_proc
    _mud_proc = Process(target=_mudproc_entrypoint)
    _mud_proc.start()
    _mud_proc.join()


def stop_tinymud(restart=False):
    if restart:
        global _restart_flag
        _restart_flag = True  # Don't quit, but restart instead
    _mud_proc.terminate()  # SIGTERM, graceful exit


if __name__ == '__main__':
    args = parse_args()

    if args.dev_db:  # Launch development database and connect to it
        print("Using Docker to start development database")
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

    # Launch app unless we received SIGINT to stop
    while _restart_flag:
        _restart_flag = False
        launch_tinymud()

    # Clean up once _quit_received is set
    if _dev_db:  # Stop development DB if it exists
        print("Killing development database")
        _dev_db.kill()
