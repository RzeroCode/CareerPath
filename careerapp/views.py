from django.http import HttpResponse
from django.shortcuts import render
from django.db import connection
import json
from careerapp import field_map
from careerapp.auto_complete_lists import auto_complete_lists
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import os.path


@csrf_exempt
def incomingQuery(request, queryType):
    query = json.loads(request.body)
    if queryType == 0:
        return queryDegreeAndCompany(request, query["degree"], query["comp"])
    if queryType == 1:
        return queryCompanyAndWhatTheyDo(request, query["comp"], query["job"])
    if queryType == 2:
        return queryUniandDegree(request, query["uni"], query["degree"])
    if queryType == 3:
        return queryUniSkillDegree(
            request, query["uni"], query["skills"], query["degree"]
        )
    if queryType == 4:
        return queryCompany(request, query["comp"])
    else:
        return HttpResponse("500 Error", status=500)


@csrf_exempt
def autoComplete(request, completeType):
    if completeType == 0:
        return HttpResponse(json.dumps(auto_complete_lists.getUniversities()))  # Uni
    if completeType == 1:
        return HttpResponse(json.dumps(auto_complete_lists.getCompanies()))  # Company
    if completeType == 2:
        return HttpResponse(json.dumps(auto_complete_lists.getDo()))  # what they do
    if completeType == 3:
        return HttpResponse(json.dumps(auto_complete_lists.getFields()))  # Field

    if completeType == 4:
        return HttpResponse(json.dumps(auto_complete_lists.getSkills()))  # skill

    else:
        return HttpResponse("500 Error", status=500)


# üniversitesi belli, bölümü belli; company, what they do, skill belli değil?:
# >koç + cs
# <company, what they do, skill


# TODO: retun what they do
def queryUniandDegree(request, uni, degree):
    # her bi companydeki çankayayı getiriyor
    query = (
        """SELECT * FROM companies JOIN LATERAL jsonb_array_elements(companies.company -> 'universities') obj(val) ON obj.val->>'uni_name' = '"""
        + uni
        + "' WHERE  company -> 'universities' @> '[{\"uni_name\":\""
        + uni
        + "\"}]';"
    )
    # query = """SELECT * FROM companies JOIN LATERAL jsonb_array_elements(companies.company -> 'universities') obj(val) ON obj.val->>'uni_name' = 'Cankaya Universitesi' WHERE  company -> 'universities' @> '[{"uni_name":"Cankaya Universitesi"}]' and obj.val->'fields' @> '[{"field_name":"computer science"}]'"""
    cursor = connection.cursor()
    cursor.execute(query)
    sql_result = cursor.fetchall()

    query_field = field_map.field_map.cs
    query_field = degree
    # sort companies based on uni_emp_count
    arr = sorted(
        sql_result,
        key=lambda company: [
            x
            for x in json.loads(company[1])["fields"]
            if x["field_name"] == query_field
        ][0]["fos_emp_count"]
        / (
            -1
            if json.loads(company[1])["uni_emp_count"] == 0
            else json.loads(company[1])["uni_emp_count"]
        ),
        reverse=True,
    )

    arr1 = [(json.loads(x[0])["company_name"], json.loads(x[1])) for x in arr]
    arr = [[json.loads(x[0])["company_name"]] for x in arr]

    # top 3 şirket döndür
    # her şirketin what they do ve skilleri olacak: company_name, what_they_do[], skill[]
    doDict = {}
    skillDict = {}
    for x in arr1[:3]:
        for field in x[1]["fields"]:
            if field["field_name"] == query_field:
                for do in field["details"]["What they do"]:
                    doDict[do["skill"]] = doDict.get(do["skill"], 0) + int(do["count"])
                    pass
                for skill in field["details"]["What they are skilled at"]:
                    skillDict[skill["skill"]] = skillDict.get(skill["skill"], 0) + int(
                        skill["count"]
                    )
                break

    doSortArr = sorted(
        doDict.items(), key=lambda theyDo: (theyDo[1], theyDo[0]), reverse=True
    )
    skillSortArr = sorted(
        skillDict.items(), key=lambda skill: (skill[1], skill[0]), reverse=True
    )
    
    trending_skills={}
    with open(os.path.join('careerapp/static/', "search_skill.json"), "r") as read_file:
        trending_skills = json.load(read_file)


    degree_skills = trending_skills[degree]
    sorted_skills = sorted(
        degree_skills,
        key=lambda skill: skill['count'],
        reverse=True
    )[:len(degree_skills)//10]
    return_skills_arr = []
    for x in [y[0] for y in skillSortArr[:5]]:
        if x in  [x['skill_name'] for x in sorted_skills]:
            return_skills_arr.append(['trend'])
        return_skills_arr.append([x])
    a = json.dumps(
        {
            "comp": arr[:4],
            "skill": return_skills_arr,
            "do": [[x[0]] for x in doSortArr],
        }
    )
    return HttpResponse(a)


# -üniversitesi belli değil, skilleri belli değil, ne okumak istiyorum belli, company belli:
# >Huawei + cs,
# <recommend uni && skill && what they do
def queryDegreeAndCompany(request, degree, company):
    # her bi companydeki çankayayı getiriyor
    query = (
        f"""SELECT * FROM companies WHERE company->>'company_name' LIKE '{company}';"""
    )
    cursor = connection.cursor()
    cursor.execute(query)
    sql_result = cursor.fetchone()[0]
    query_field = field_map.field_map.cs
    query_field = degree

    universities = json.loads(sql_result)["universities"]

    BASE = os.path.dirname(os.path.abspath(__file__))

    uni_alumni = 0
    with open(
        os.path.join(BASE, "universities_alumni_number_dict.json"), "r"
    ) as read_file:
        uni_alumni = json.load(read_file)

    arr2 = sorted(
        universities,
        key=lambda university: (
            [x for x in university["fields"] if x["field_name"] == query_field][0][
                "fos_emp_count"
            ]
            / uni_alumni[university["uni_name"]]
        ),
        reverse=True,
    )
    doDict = {}
    skillDict = {}

    skillsarr = []
    for x in arr2[:3]:
        print(x["uni_name"])
        for field in x["fields"]:
            if field["field_name"] == query_field:
                for do in field["details"]["What they do"]:
                    doDict[do["skill"]] = doDict.get(do["skill"], 0) + int(do["count"])
                for skill in field["details"]["What they are skilled at"]:
                    skillDict[skill["skill"]] = skillDict.get(skill["skill"], 0) + int(
                        skill["count"]
                    )
                z = [q["skill"] for q in field["details"]["What they do"]]
                c = [q["skill"] for q in field["details"]["What they are skilled at"]]
                skillsarr.append(z)
                skillsarr.append(c)
                break
    doSortArr = sorted(
        doDict.items(), key=lambda theyDo: (theyDo[1], theyDo[0]), reverse=True
    )
    skillSortArr = sorted(
        skillDict.items(), key=lambda skill: (skill[1], skill[0]), reverse=True
    )

    trending_skills={}
    with open(os.path.join('careerapp/static/', "search_skill.json"), "r") as read_file:
        trending_skills = json.load(read_file)
    degree_skills = trending_skills[degree]
    sorted_skills = sorted(
        degree_skills,
        key=lambda skill: skill['count'],
        reverse=True
    )[:len(degree_skills)//10]
    return_skills_arr = []
    for x in [y[0] for y in skillSortArr[:5]]:
        if x in  [x['skill_name'] for x in sorted_skills]:
            return_skills_arr.append(['trend'])
        return_skills_arr.append([x])

    a = json.dumps(
        {
            "uni": [[x["uni_name"]] for x in arr2][:3],
            "skill": return_skills_arr,
            "do": [[x[0]] for x in doSortArr[:5]],
        }
    )
    return HttpResponse(a)


# üniversitesi belli değil, skilleri belli değil, what they do belli, company belli:
# >Huawei + SDE
# <recommend uni && skill && bölüm
def queryCompanyAndWhatTheyDo(request, company, what_they_do):
    query = (
        f"""SELECT * FROM companies WHERE company->>'company_name' LIKE '{company}';"""
    )
    cursor = connection.cursor()
    cursor.execute(query)
    sql_result = cursor.fetchone()[0]
    universities = json.loads(sql_result)["universities"]
    what_they_do_dict = {}
    for university in universities:
        uni_sum = 0
        for field in university["fields"]:
            for wtd in field["details"]["What they do"]:
                if wtd["skill"] == what_they_do:
                    uni_sum += int(wtd["count"])
        what_they_do_dict[university["uni_name"]] = (uni_sum, university)
    arr = sorted(
        what_they_do_dict.values(), key=lambda university: university[0], reverse=True
    )
    arr = [x[1]["uni_name"] for x in arr]
    arr_uni = []
    arr_area = []
    arr_skills = []
    for x in arr[:3]:
        what_they_do_dict2 = {}
        university = what_they_do_dict[x][1]
        print(university["uni_name"])
        arr_uni.append([university["uni_name"]])
        for field in university["fields"]:
            for wtd in field["details"]["What they do"]:
                if wtd["skill"] == what_they_do:
                    what_they_do_dict2[field["field_name"]] = (int(wtd["count"]), field)

    arr2 = sorted(
        what_they_do_dict2.values(),
        key=lambda university: university[0],
        reverse=True,
    )
    arr2 = [x[1]["field_name"] for x in arr2]
    print(arr2)
    arr_area = [[x] for x in arr2[:3]]
    print("-----------")
    for s in arr2[:3]:
        for x in university["fields"]:
            if x["field_name"] == s:
                print(s, x["details"]["What they are skilled at"][:5])
                arr_skills.extend(x["details"]["What they are skilled at"][:5])
    skillDict = {}
    for skill in arr_skills:
        skillDict[skill["skill"]] = skillDict.get(skill["skill"], 0) + int(
            skill["count"]
        )
    skillSortArr = sorted(
        skillDict.items(), key=lambda skill: (skill[1], skill[0]), reverse=True
    )

    trending_skills={}
    with open(os.path.join('careerapp/static/', "search_skill.json"), "r") as read_file:
        trending_skills = json.load(read_file)
    degree_skills = []
    for x in [trending_skills[x[0]] for x in arr_area]:
        degree_skills.extend(x)
    sorted_skills = sorted(
        degree_skills,
        key=lambda skill: skill['count'],
        reverse=True
    )[:len(degree_skills)//10]
    return_skills_arr = []
    for x in [y[0] for y in skillSortArr[:5]]:
        if x in  [x['skill_name'] for x in sorted_skills]:
            return_skills_arr.append(['trend'])
        return_skills_arr.append([x])
    a = json.dumps({"uni": arr_uni, "field": arr_area, "skill": return_skills_arr})

    return HttpResponse(a)


# > Sabancı + Java + CS
# < recommend comp && what they do
def queryUniSkillDegree(request, uni, userSkills, degree):
    # her bi companydeki çankayayı getiriyor
    query = (
        """SELECT * FROM companies JOIN LATERAL jsonb_array_elements(companies.company -> 'universities') obj(val) ON obj.val->>'uni_name' = '"""
        + uni
        + "' WHERE  company -> 'universities' @> '[{\"uni_name\":\""
        + uni
        + "\"}]';"
    )
    userSkills= userSkills.split(',')
    cursor = connection.cursor()
    cursor.execute(query)
    sql_result = cursor.fetchall()

    query_field = field_map.field_map.cs
    query_field = degree
    # sort companies based on uni_emp_count
    arr = sorted(
        sql_result,
        key=lambda company: [
            x
            for x in json.loads(company[1])["fields"]
            if x["field_name"] == query_field
        ][0]["fos_emp_count"]
        / (
            -1
            if json.loads(company[1])["uni_emp_count"] == 0
            else json.loads(company[1])["uni_emp_count"]
        ),
        reverse=True,
    )

    return_dict = {}
    arr1 = [(json.loads(x[0])["company_name"], json.loads(x[1])) for x in arr]

    companies_ranking = {}

    for userSkill in userSkills:
        skillsDict = {}
        # TODO: sort companies by user skill.
        for company in arr1[:5]:
            for field in company[1]["fields"]:
                if field["field_name"] == degree:
                    for skill in field["details"]["What they are skilled at"]:
                        if skill["skill"] == userSkill:
                            skillsDict[company[0]] = (int(skill["count"]), company)
                            break
                        else:
                            skillsDict[company[0]] = (0, company)
        arrx = sorted(skillsDict.values(), key=lambda company: company[0], reverse=True)
        for x in arrx:
            if x[1][0] not in companies_ranking.keys():
                companies_ranking[x[1][0]] = [x[0], x[1][1]]
            else:
                companies_ranking[x[1][0]][0] += companies_ranking[x[1][0]][0]

    arrk = sorted(
        companies_ranking.items(),
        key=lambda company: (company[1][0], company[0]),
        reverse=True,
    )
    doDict = {}
    for x in arrk[:3]:
        for field in x[1][1]["fields"]:
            if field["field_name"] == query_field:
                for do in field["details"]["What they do"]:
                    doDict[do["skill"]] = doDict.get(do["skill"], 0) + int(do["count"])
    doSortArr = sorted(
        doDict.items(), key=lambda theyDo: (theyDo[1], theyDo[0]), reverse=True
    )
    a = json.dumps({
        "comp": [[x[0]] for x in arrk[:3]],
        "do": [[x[0]] for x in doSortArr[:5]]})
    return HttpResponse(a)


# < company
# > Uni / area / what they do / skills
def queryCompany(request, company):
    query = (
        f"""SELECT * FROM companies WHERE company->>'company_name' LIKE '{company}';"""
    )
    cursor = connection.cursor()
    cursor.execute(query)
    sql_result = cursor.fetchone()[0]

    universities = json.loads(sql_result)["universities"]

    BASE = os.path.dirname(os.path.abspath(__file__))

    uni_alumni = 0
    with open(
        os.path.join(BASE, "universities_alumni_number_dict.json"), "r"
    ) as read_file:
        uni_alumni = json.load(read_file)

    universitiesArray = sorted(
        universities,
        key=lambda university: (
            university["uni_emp_count"] / uni_alumni[university["uni_name"]]
        ),
        reverse=True,
    )
    fields = [
        field_map.field_map.cs,
        field_map.field_map.ce,
        field_map.field_map.it,
        field_map.field_map.cse,
        field_map.field_map.eee,
        field_map.field_map.eec,
        field_map.field_map.me,
        field_map.field_map.mrae,
    ]
    fieldsArray = sorted(
        [
            [
                field,
                sum(
                    z[0]
                    for z in [
                        [
                            y["fos_emp_count"]
                            for y in x["fields"]
                            if y["field_name"] == field
                        ]
                        for x in universitiesArray
                    ]
                ),
            ]
            for field in fields
        ],
        key=lambda field: field[0],
        reverse=True,
    )
    print(fieldsArray)

    doDict = {}
    skillDict = {}

    for university in universities:
        for field in university["fields"]:
            for do in field["details"]["What they do"]:
                doDict[do["skill"]] = doDict.get(do["skill"], 0) + int(do["count"])
                pass
            for skill in field["details"]["What they are skilled at"]:
                skillDict[skill["skill"]] = skillDict.get(skill["skill"], 0) + int(
                    skill["count"]
                )

    doSortArr = sorted(
        doDict.items(), key=lambda theyDo: (theyDo[1], theyDo[0]), reverse=True
    )
    skillSortArr = sorted(
        skillDict.items(), key=lambda skill: (skill[1], skill[0]), reverse=True
    )
    trending_skills={}
    with open(os.path.join('careerapp/static/', "search_skill.json"), "r") as read_file:
        trending_skills = json.load(read_file)
    degree_skills = []
    for x in [trending_skills[x[0]] for x in fieldsArray]:
        degree_skills.extend(x)
    sorted_skills = sorted(
        degree_skills,
        key=lambda skill: skill['count'],
        reverse=True
    )[:len(degree_skills)//10]
    return_skills_arr = []
    for x in [y[0] for y in skillSortArr[:5]]:
        if x in  [x['skill_name'] for x in sorted_skills]:
            return_skills_arr.append(['trend'])
        return_skills_arr.append([x])
    print(doSortArr)
    print(skillSortArr)
    
    returnDict = {
        "uni": [[x["uni_name"]] for x in universitiesArray][:3],
        "field": [[x[0]] for x in fieldsArray[:3]],
        "do": [[x[0]] for x in doSortArr[:5]],
        "skill": return_skills_arr,
    }
    return HttpResponse(json.dumps(returnDict))


# render html page
def careerapp(request):

    return render(request, "careerapp/careerapp.html")
