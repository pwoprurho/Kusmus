from ics import Calendar, Event
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class CalendarService:
    @staticmethod
    def create_schedule(roadmap, start_date=None):
        """
        Generates an ICS calendar file content string from a roadmap.
        """
        if start_date is None:
            start_date = datetime.now()

        c = Calendar()
        
        # Estimate: 1 step = 2 days of study (configurable)
        days_per_step = 2
        
        current_date = start_date

        for step in roadmap.steps:
            e = Event()
            e.name = f"Study: {step.title}"
            e.begin = current_date
            e.duration = timedelta(hours=2) # 2 hours study session
            e.description = f"{step.description}\n\nGoal: {roadmap.goal}"
            
            c.events.add(e)
            
            # Move to next schedule slot (e.g., next day)
            current_date += timedelta(days=days_per_step)

        return str(c)
