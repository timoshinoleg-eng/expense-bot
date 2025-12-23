"""Middleware for FSM state timeout.

Automatically clears FSM state if user doesn't interact for specified time.
This prevents incomplete transactions from persisting indefinitely.
"""

from datetime import datetime, timedelta
from typing import Callable, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import Message
from aiogram.fsm.context import FSMContext


class FSMTimeoutMiddleware(BaseMiddleware):
    """Middleware that resets FSM state after timeout period.
    
    Default timeout: 5 minutes.
    Can be customized when instantiating.
    """

    def __init__(self, timeout_minutes: int = 5):
        """Initialize middleware with timeout duration.
        
        Args:
            timeout_minutes: Minutes to wait before clearing FSM state.
        """
        self.timeout = timedelta(minutes=timeout_minutes)
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[Message, Any], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        """Check timeout and clear state if needed."""
        state: FSMContext = data.get("state")
        
        if state is None:
            return await handler(event, data)

        current_state = await state.get_state()
        
        # Only apply timeout to states (not when state is None)
        if current_state:
            state_data = await state.get_data()
            now = datetime.now()
            
            # Get or initialize last_activity timestamp
            last_activity = state_data.get(
                "_last_activity", now
            )
            
            # If last_activity is a string, parse it
            if isinstance(last_activity, str):
                try:
                    last_activity = datetime.fromisoformat(last_activity)
                except (ValueError, TypeError):
                    last_activity = now
            
            # Check if timeout exceeded
            if now - last_activity > self.timeout:
                # Timeout exceeded - clear state
                await state.clear()
                await event.answer(
                    "⏱️ Время сеанса истекло.\n"
                    "Ввод отменён. Начните заново."
                )
                # Don't call the handler - return early
                return
            
            # Update last activity timestamp
            await state.update_data(
                _last_activity=now.isoformat()
            )
        
        # Continue to handler
        return await handler(event, data)
