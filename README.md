# Last.fm Scrobbler for ONDA

External `python-v1` scrobbling provider for ONDA. It sends Now Playing updates
and qualified listens through the current Last.fm Scrobbling API.

## Configuration

Last.fm requires credentials belonging to an API application and an authorized
user session:

1. Create or open an API account at `https://www.last.fm/api/account/create`.
2. Obtain its API key and shared secret.
3. Complete Last.fm's desktop authentication flow to obtain a session key.
4. Install the `.meb`, enter all three values in ONDA and press **Probar**.

ONDA encrypts the three values in plugin-isolated storage. The provider never
stores or logs them. The plugin deliberately does not request a Last.fm password.

## Build

From the ONDA repository:

```powershell
dart run .\tools\meb_cli\bin\meb.dart validate ..\onda-lastfm-scrobble-provider
dart run .\tools\meb_cli\bin\meb.dart build ..\onda-lastfm-scrobble-provider
```

## Test

```powershell
python -m unittest discover -s .\tests -v
```
