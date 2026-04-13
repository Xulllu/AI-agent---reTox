# core/software_agent.py

from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Optional
import asyncio

TPercept = TypeVar('TPercept')
TAction = TypeVar('TAction')
TResult = TypeVar('TResult')

class SoftwareAgent(ABC, Generic[TPercept, TAction, TResult]):
    """
    Bazna klasa za sve agente - framework sloj
    Implementira Sense → Think → Act ciklus
    """
    
    @abstractmethod
    async def sense(self) -> Optional[TPercept]:
        """
        PERCEPCIJA - prikuplja informacije iz okruženja
        Returns: Percept objekat ili None ako nema posla
        """
        pass
    
    @abstractmethod
    async def think(self, percept: TPercept) -> TAction:
        """
        RASUĐIVANJE - donosi odluku na osnovu percepta
        Args: percept - informacije iz okruženja
        Returns: Action - šta treba uraditi
        """
        pass
    
    @abstractmethod
    async def act(self, action: TAction) -> TResult:
        """
        AKCIJA - izvršava odluku i mijenja svijet
        Args: action - odluka koju treba izvršiti
        Returns: Result - rezultat akcije
        """
        pass
    
    async def step(self) -> Optional[TResult]:
        agent_name = self.__class__.__name__

        def emit(phase: str, message: str):
            db = getattr(self, "db", None)
            if db and hasattr(db, "save_agent_event"):
                try:
                    db.save_agent_event(agent_name, phase, message)
                except Exception:
                    pass

        emit("sense", "tick started")
        percept = await self.sense()
        if percept is None:
            emit("sense", "no work")
            return None

        emit("sense", f"percept={percept.__class__.__name__}")
        action = await self.think(percept)
        emit("think", f"action={action.__class__.__name__}")

        result = await self.act(action)
        emit("act", f"result={result.__class__.__name__}")
        return result