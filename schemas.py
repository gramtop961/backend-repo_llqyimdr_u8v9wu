"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name.
"""
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


class Game(BaseModel):
    """
    Tic Tac Toe game sessions
    Collection name: "game"
    """
    game_id: str = Field(..., min_length=4, max_length=4, description="4-digit game code")
    board: List[Optional[Literal['X', 'O']]] = Field(
        default_factory=lambda: [None] * 9,
        description="Board state as 9 positions"
    )
    x_starts: bool = Field(True, description="Who starts the current round")
    x_is_next: bool = Field(True, description="Whose turn it is now")
    x_player: Optional[str] = Field(None, description="Identifier for player X")
    o_player: Optional[str] = Field(None, description="Identifier for player O")
    winner: Optional[Literal['X', 'O']] = Field(None, description="Winner of the current round if any")
    draw: bool = Field(False, description="Whether the current round is a draw")
    score_x: int = Field(0, ge=0)
    score_o: int = Field(0, ge=0)

    @field_validator('board')
    @classmethod
    def board_length(cls, v: List[Optional[str]]):
        if len(v) != 9:
            raise ValueError('Board must have 9 positions')
        return v
