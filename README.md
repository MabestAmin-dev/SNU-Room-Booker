# SNU Practice Room Bot

Automation script for SNU SSIMS room booking.

## How to run
- Python 3.12+
- `pip install -r requirements.txt`
- Ensure Chrome installed.
- Uses a dedicated Chrome profile at `C:\SNU_Booker\chrome_snu_profile`.

## Schedule on Windows
- Use Task Scheduler to run `run_snu_bot.bat` at 01:00 KST on selected days.

## Notes
- Do **not** commit `chrome_snu_profile/` or debug screenshots.
