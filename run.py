import os

from portal.app import create_app

app = create_app()

if __name__ == "__main__":
    # Port 5000 is taken by AirPlay Receiver on macOS, so default to 8000.
    app.run(debug=True, port=int(os.getenv("PORT", "8000")))
