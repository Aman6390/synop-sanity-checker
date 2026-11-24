import os
import sys
import webbrowser
import uvicorn

if __name__ == "__main__":
    print("=" * 65)
    print("   IMD SYNOP Sanity & SLA Timeliness Monitor")
    print("   Ingesting from https://amssdelhi.gov.in/sendata/sendata.txt")
    print("   Starting backend server on http://127.0.0.1:8000 ...")
    print("=" * 65)

    # Open browser after short delay
    webbrowser.open("http://127.0.0.1:8000")

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)
