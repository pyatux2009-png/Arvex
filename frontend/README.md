# ArbX Frontend

Dark black/orange React + TypeScript + Vite control panel.

## Windows — exact startup

Open PowerShell **inside the `frontend` folder**, where `package.json` is located:

```powershell
npm.cmd install
npm.cmd run dev
```

Vite should print:

```text
Local:   http://localhost:5173/
Network: http://<your-pc-ip>:5173/
```

Open `http://localhost:5173/` in the browser.

If `localhost` does not open, try `http://127.0.0.1:5173/`.

Do **not** run `npm.cmd install` from `C:\Windows\System32`.

## Backend

In a second PowerShell window, from the project root:

```powershell
py -m pip install -r requirements.txt
py run_backend.py
```

Backend health page:

```text
http://127.0.0.1:8000/api/health
```

API docs:

```text
http://127.0.0.1:8000/docs
```

The frontend defaults to `http://127.0.0.1:8000`. To change it, copy `.env.example` to `.env` and edit `VITE_API_URL`.
