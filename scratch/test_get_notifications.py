import asyncio
import sys
from pathlib import Path

# Add root folder to sys.path
root_dir = Path(__file__).resolve().parents[1]
sys.path.append(str(root_dir))

from app.services.notification_service import NotificationService

async def test_get():
    service = NotificationService()
    user_id = '9ef4742bf59ff11188775db58cef45d2bbfd50c7424f68291c39beeaa3d5a62e'
    try:
        res = await service.get_user_notifications(user_id=user_id)
        print("Success! Got result:")
        print(res)
    except Exception as e:
        print("Error encountered:")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_get())
