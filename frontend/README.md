# Getting Started with Create React App

This project was bootstrapped with Create React App.

In the /frontend directory, you can run:

### `npm start`

Runs the app in the development mode.\
Open [http://localhost:3000](http://localhost:3000) to view it in your browser.

The page will reload when you make changes.\
You may also see any lint errors in the console.

From the project root, you can run both frontend and backend together:

### `npm run dev:all`

Starts React on port 3001 and Flask on port 5000 in one terminal.

In the /backend directory, you can run:

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. python api/index.py
Open [http://localhost:5000](http://localhost:5000) to view server status in your browser.
