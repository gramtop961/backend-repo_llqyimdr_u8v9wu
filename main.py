import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from database import db
from schemas import Game

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

COLL = "game"


def calculate_winner(board):
    lines = [
        (0, 1, 2), (3, 4, 5), (6, 7, 8),
        (0, 3, 6), (1, 4, 7), (2, 5, 8),
        (0, 4, 8), (2, 4, 6)
    ]
    for a, b, c in lines:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    return None


def get_game_or_none(game_id: str):
    return db[COLL].find_one({"game_id": game_id})


def serialize_game(doc):
    if not doc:
        return None
    return {
        "game_id": doc.get("game_id"),
        "board": doc.get("board", [None] * 9),
        "x_starts": doc.get("x_starts", True),
        "x_is_next": doc.get("x_is_next", True),
        "x_player": doc.get("x_player"),
        "o_player": doc.get("o_player"),
        "winner": doc.get("winner"),
        "draw": doc.get("draw", False),
        "score_x": doc.get("score_x", 0),
        "score_o": doc.get("score_o", 0),
    }


class JoinRequest(BaseModel):
    game_id: str
    player_id: str


@app.post("/api/game/join")
def join_game(payload: JoinRequest):
    gid = payload.game_id
    pid = payload.player_id
    if not (gid and len(gid) == 4 and gid.isdigit()):
        raise HTTPException(status_code=400, detail="game_id must be a 4-digit code")

    game = get_game_or_none(gid)

    # Create new game if it doesn't exist
    if not game:
        new_game = Game(game_id=gid).model_dump()
        new_game["x_player"] = pid
        db[COLL].insert_one(new_game)
        game = new_game
        role = "X"
    else:
        # Determine role
        if game.get("x_player") == pid:
            role = "X"
        elif game.get("o_player") == pid:
            role = "O"
        elif not game.get("x_player"):
            db[COLL].update_one({"game_id": gid}, {"$set": {"x_player": pid}})
            role = "X"
            game["x_player"] = pid
        elif not game.get("o_player"):
            db[COLL].update_one({"game_id": gid}, {"$set": {"o_player": pid}})
            role = "O"
            game["o_player"] = pid
        else:
            raise HTTPException(status_code=409, detail="Game already has two players")

    return {"role": role, "game": serialize_game(game)}


@app.get("/api/game/{game_id}")
def get_game(game_id: str):
    game = get_game_or_none(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return serialize_game(game)


class MoveRequest(BaseModel):
    index: int
    role: str  # 'X' or 'O'
    player_id: str


@app.post("/api/game/{game_id}/move")
def make_move(game_id: str, payload: MoveRequest):
    game = get_game_or_none(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    if payload.role not in ("X", "O"):
        raise HTTPException(status_code=400, detail="Invalid role")

    # Validate player identity
    if payload.role == "X" and game.get("x_player") != payload.player_id:
        raise HTTPException(status_code=403, detail="Not authorized as X")
    if payload.role == "O" and game.get("o_player") != payload.player_id:
        raise HTTPException(status_code=403, detail="Not authorized as O")

    # If round over, reject
    if game.get("winner") or game.get("draw"):
        raise HTTPException(status_code=409, detail="Round already finished")

    # Validate turn
    if (payload.role == "X" and not game.get("x_is_next", True)) or (
        payload.role == "O" and game.get("x_is_next", True)
    ):
        raise HTTPException(status_code=409, detail="Not your turn")

    idx = payload.index
    if idx < 0 or idx > 8:
        raise HTTPException(status_code=400, detail="Invalid index")

    board = game.get("board", [None] * 9)
    if board[idx] is not None:
        raise HTTPException(status_code=409, detail="Square already filled")

    # Apply move
    board[idx] = payload.role
    winner = calculate_winner(board)
    draw = False
    score_x = game.get("score_x", 0)
    score_o = game.get("score_o", 0)

    if winner:
        if winner == "X":
            score_x += 1
        else:
            score_o += 1
    elif all(v is not None for v in board):
        draw = True

    x_is_next = not game.get("x_is_next", True)

    db[COLL].update_one(
        {"game_id": game_id},
        {
            "$set": {
                "board": board,
                "x_is_next": x_is_next,
                "winner": winner,
                "draw": draw,
                "score_x": score_x,
                "score_o": score_o,
            }
        },
    )

    updated = get_game_or_none(game_id)
    return serialize_game(updated)


@app.post("/api/game/{game_id}/reset-round")
def reset_round(game_id: str):
    game = get_game_or_none(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    # Alternate starting player each round for fairness
    next_starter_is_x = not game.get("x_starts", True)
    db[COLL].update_one(
        {"game_id": game_id},
        {
            "$set": {
                "board": [None] * 9,
                "winner": None,
                "draw": False,
                "x_starts": next_starter_is_x,
                "x_is_next": next_starter_is_x,
            }
        },
    )

    updated = get_game_or_none(game_id)
    return serialize_game(updated)


@app.post("/api/game/{game_id}/reset-scores")
def reset_scores(game_id: str):
    game = get_game_or_none(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    db[COLL].update_one(
        {"game_id": game_id},
        {"$set": {"score_x": 0, "score_o": 0, "board": [None] * 9, "winner": None, "draw": False, "x_is_next": game.get("x_starts", True)}},
    )

    updated = get_game_or_none(game_id)
    return serialize_game(updated)


@app.get("/")
def read_root():
    return {"message": "Tic Tac Toe API running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": [],
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, "name") else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    import os as _os
    response["database_url"] = "✅ Set" if _os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if _os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
