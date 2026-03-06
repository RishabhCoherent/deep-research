"""Start the backend API server."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("backend.api:app", reload=True, port=8000)
