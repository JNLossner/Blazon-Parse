import webbrowser

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="Blazon Parse")

HOST = "127.0.0.1"
PORT = 8000


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return "<h1>Blazon Parse</h1><p>Interface coming soon.</p>"


def run() -> None:
    webbrowser.open(f"http://{HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    run()
