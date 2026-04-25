"""MellowDLP entry point."""
import sys, logging

def main():
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    try:
        from flaskwebgui import FlaskUI
    except ImportError:
        print("ERROR: flaskwebgui not installed. Run SETUP.bat first.")
        input("Press Enter..."); sys.exit(1)
    try:
        from server import app
    except Exception as e:
        print(f"ERROR loading server: {e}")
        input("Press Enter..."); sys.exit(1)

    # flaskwebgui opens Edge/Chrome in app mode automatically
    # Translate is blocked via HTML meta tags in index.html
    ui = FlaskUI(app=app, server="flask", width=1300, height=840, fullscreen=False)
    ui.run()

if __name__ == "__main__":
    main()
