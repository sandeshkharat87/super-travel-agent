from fastapi import FastAPI, HTTPException
from fastapi import Request
# from langchain_openai.chat_models import ChatOpenAI
from langchain_groq.chat_models import ChatGroq
from pydantic import BaseModel

from dotenv import load_dotenv
load_dotenv()

# _llm = ChatOpenAI(model="gpt-4o-mini",temperature=0.1)
_llm = ChatGroq(model="openai/gpt-oss-20b",temperature=0.1)

app = FastAPI()



class ChatRequest(BaseModel):
    question: str
    

@app.post("/chat")
def chat(data:ChatRequest):
    Question = data.question
    
    try:
        if Question:
            response = _llm.invoke(Question)
            return {"data": response.content}
        else:
            raise HTTPException(status_code=400, detail="Question is required")
    except Exception as e:
        print("Error:",e) 
        raise HTTPException(status_code=500, detail="Internal Server Error")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
    
    
app ->
    api- [chat, test, db]
    services [llm, database, redis]
    schemas [Input , op]
    excetiopns [cstm ]
    configs [envs]
    
    main.py
    .env