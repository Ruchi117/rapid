<<<<<<< HEAD
# RapidResQ

RapidResQ contains a Vite/React dispatch dashboard and a separate Flask/SQLite demo application. The public Vercel deployment runs the Vite dashboard; it does not call the Flask app.

## Vite dashboard

```sh
npm install
npm run dev
```

The dashboard includes driver, patient-monitor, and hospital views; simulated emergency registration; equipment-aware ambulance assignment; OSRM road routing with labeled estimates when routing is unavailable; capability-based hospital comparison; vital alerts and updates; explicit trip transitions; handover and ambulance release; and browser-persisted incident history.

## Flask/SQLite demo

The existing Python implementation is independent of the Vite dashboard and can be run locally:

```sh
python -m pip install -r static/requirements.txt
python app.py
```

This starts Flask's development server. It uses `intelliresq.db` and its own sample-data UI/API; it is not the backend for the Vite dashboard.

## Verify the Vite dashboard

```sh
npm test
npm run lint
npm run build
```

## Data and deployment limitations

- Patient details and vital readings entered in the Vite dashboard are demo data. Ambulance positions, response estimates, and facility capability records are simulated; the Flask screen also labels its sample locations, vehicle movement, capacity, and vital readings as training data. Neither app has live GPS, live traffic, sensors, or verified hospital availability.
- The Vite dashboard stores its incident history in this browser's `localStorage`. Its views share the same browser state, but it does not synchronize between browsers or operators. Clearing site data removes it.
- The Flask demo stores records in SQLite. A host with an ephemeral filesystem can lose its database on restart or redeploy; the Flask database is not attached to the Vercel deployment.
- Road routes in the Vite dashboard use the public OSRM demo service when available. On failure, a clearly labeled straight-line-derived fallback estimate is shown. OpenStreetMap tiles and routing require internet access.
- Neither app is for clinical use or real emergency dispatch.

## Deploy to Vercel

The included `vercel.json` builds and serves the Vite dashboard (`npm run build`, output `dist`). No secrets or environment variables are needed. This does not deploy the Flask server. A multi-operator service needs a separately deployed Flask API and durable database; configure and authorize those services before relying on cross-device or long-term server-side history. No paid storage is configured.
=======
# rapid
>>>>>>> 79887456dac5c2dcb5fbbcc146a3297c34c56ec8
