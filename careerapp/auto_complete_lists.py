from django.db import connection
import json

class auto_complete_lists:
    _universities: list = []
    _companies:list = []
    _fields:list = []
    _dos:list = []
    _skills:list =[]

    
    def getUniversities() -> list:
        if len(auto_complete_lists._universities) == 0:
            with open('careerapp/static/universities.json','r') as f:
                auto_complete_lists._universities = f.read()
                auto_complete_lists._universities = json.loads(auto_complete_lists._universities)
            pass
        return auto_complete_lists._universities
    def getCompanies() -> list:        
        if len(auto_complete_lists._companies) == 0  :
            query = (f"""SELECT company->>'company_name' FROM companies""")
            cursor = connection.cursor()
            cursor.execute(query)
            auto_complete_lists._companies = [x[0] for x in cursor.fetchall()]
        return auto_complete_lists._companies
    def getFields() -> list:
        if len(auto_complete_lists._fields) == 0  :
            with open('careerapp/static/fieldofstudy.json','r') as f:
                auto_complete_lists._fields = json.loads(f.read())
            pass
        return auto_complete_lists._fields
    def getDo() -> list:
        if len(auto_complete_lists._dos) == 0  :
            with open('careerapp/static/whattheydo-copy.json','r') as f:
                auto_complete_lists._dos = json.loads(f.read())
        return auto_complete_lists._dos
    def getSkills() -> list:
        if len(auto_complete_lists._skills) == 0  :
            with open('careerapp/static/search_skill-copy.json','r') as f:
                auto_complete_lists._skills = json.loads(f.read())
        return auto_complete_lists._skills