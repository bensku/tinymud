# Tinymud
Tinymud is a (not so) tiny web-based text adventure game engine.
DUNGEON is a (actually) tiny sample game based on it.

## Features
* Create accounts and enter the world with *characters*
* Explore hyperlinked *places* with (rich) text descriptions
* Persistent world and characters (in PostgreSQL database)

For admin/editor characters, also
* Create, edit and delete places with Markdown-like format

### Features that didn't make it
... in order they would've been implemented.

* Seeing characters of other players
  * Backend is *mostly* ready, but logout handling was not finished
* Items and attributes of player characters
  * Some *rewards* for gameplay, instead of just reading text
* NPCs and monsters
  * Some AI would be needed for this to be useful

## Requirements
[Pipenv](https://github.com/pypa/pipenv) is used for dependency management.
Tinymud needs the following *additional* things installed:

* Linux
  * Other Unixes might work, Windows probably won't
  * Porting should be reasonable easy, this is Python after all
* Python 3.9
* PostgreSQL (for production)
* Docker (for development databases)

## Development
When installing the dependencies, remember development dependencies!
```
pipenv install --dev
cd client
npm install
```

To start Tinymud, use <code>pipenv run tinymud</code>.
The frontend will be served at <code>localhost:8080</code>.

### Development database
Manually setting up and periodically clearing a PostgreSQL databases while
developing is annoying. Because no embedded database supports same SQL
features, Tinymud uses Docker to provide disposable test databases.

Just pass <code>--dev-db</code> as an argument. A database container will be
created and connected to automatically. It will also be deleted once Tinymud
stops.

### Live-reloading
Tinymud can reload itself when the source code changes on disk. This is enabled
by setting <code>--watch=core</code> argument. This is experimental and not very
stable feature, so beware.

## Testing
Backend has a few unit tests written with Pytest:
```
pipenv run test
```
It has been configured to automatically detect files with names ending
<code>_test.py</code>. Separate directories for tests are not used.

Frontend also has a few tests written with Jest:
```
npm test
```
They are similarly autodetected from <code>.test.ts</code> postfixes.
Note that they are currently ran with Node, so e.g. testing HTML sanitization
with DOMPurify is not possible.

## Production deployment
When deploying, do not let Pipenv or npm upgrade dependencies!
```
pipenv install --deploy
cd client
npm ci
```
Note that NPM will also install dev dependencies; they are never part of the
bundled JS.

When starting the backend, remember to specify database URL and toggle on
the production mode:
```
pipenv run tinymud --prod --db=postgres://user:password@host:port/tinymud
```
The backend currently serves the frontend even in production mode.
This *should* be changed in future, but I ran out of time.

HTTPS is not supported out of the box, so using a reverse proxy is strongly
recommended.

## Retrospective
Games, even text-based ones are *very* time-consuming to implement. This
project might be somewhat impressive technically, but the main game loop is
missing.

I'm quite happy with the code quality and architecture of Tinymud. Making a
real game out of this should be just matter of time - it is unlikely that
everything would need to be rewritten from ground up.

That being said, there are a few technical difficulties I wish I could have
predicted...

* VSCode Python support and Python tooling in general is not *that* great
  * Type hints are still a pain point
  * ... especially when aiming for 100% Mypy strict mode compliance
* asyncio function coloring is annoying to work around
  * Constructors can't (or at least shouldn't) be made async
  * Static analysis tools don't recognize missing awaits
  * Greenlets might've been better choice
  * A language with proper coroutines (e.g. Lua, soon Java) would have helped
* Writing even a very simple ORM is difficult
  * Combine this with asyncio function coloring for a lot of *fun*
  * Satisfied with the result, but it took a while
* Some data could have benefined from NoSQL storage
  * PostgreSQL JSON might have been better for passages between places
* Writing a very dynamic UI with Vanilla JavaScript is not... ideal
  * But learning React in a few weeks would've been worse
  * Also, my UI design skills are still lacking
* Python performance is questionable
  * It is fast enough... for a tiny game with few concurrent players