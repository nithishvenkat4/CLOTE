from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"message": "CLOTE server is running"}

@app.get("/health")
def health():
    return {"status": "online", "project": "CLOTE"}
