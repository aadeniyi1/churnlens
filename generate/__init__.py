"""
generate/: builds the fake "source system" data that the rest of ChurnLens uses.

In a real company this data would come from a CRM (accounts, contracts), the
product's event logs (usage), and a help desk (tickets). We create all three with
code so the project is free, private, and the same on every machine.

Run order (run.py does this for you):
    accounts.py -> contracts.py -> usage.py -> tickets.py
Each step reads the files written by the step before it.
"""
