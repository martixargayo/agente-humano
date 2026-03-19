from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import app


def main() -> None:
    client = TestClient(app, raise_server_exceptions=False)

    pages = [
        '/interfaz_usuario',
        '/interfaz_usuario/',
        '/interfaz_usuario/negociacion',
        '/interfaz_usuario/negociacion/',
        '/interfaz_usuario/negociacion-validacion',
        '/interfaz_usuario/negociacion-validacion/',
    ]
    assets = [
        '/interfaz_usuario/app.js',
        '/interfaz_usuario/feedback_report_view.js',
        '/interfaz_usuario/avatar_runtime/bootstrap.js',
    ]

    print('[pages]')
    for path in pages:
        r = client.get(path)
        print(path, r.status_code)

    print('\n[assets]')
    for path in assets:
        r = client.get(path)
        preview = r.text[:80].replace('\n', ' ')
        print(path, r.status_code, preview)

    html = client.get('/interfaz_usuario/negociacion-validacion/').text
    print('\n[html_asset_paths]')
    for marker in [
        '/interfaz_usuario/app.js',
        '/interfaz_usuario/feedback_report_view.js',
        '/interfaz_usuario/avatar_runtime/bootstrap.js',
    ]:
        print(marker, marker in html)

    app_js = client.get('/interfaz_usuario/app.js').text
    print('\n[js_contract_checks]')
    print('readPublicSlugFromUrl', 'function readPublicSlugFromUrl()' in app_js)
    print('bootstrapPayload', 'function bootstrapPayload()' in app_js)
    print('resultado=ok')


if __name__ == '__main__':
    main()
