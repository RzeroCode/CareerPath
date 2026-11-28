"""DegreeMatcher against made-up job-ad sentences (cases from the Step 2 test plan)."""
import pytest

from careers.matching import DegreeMatcher

# The terms the 8 engineering program types are seeded with; CS also counts as CE (a degree term both share).
PROGRAMS = [
    ("CE", ["Computer Engineering", "Bilgisayar Mühendisliği", "Computer Science", "Bilgisayar Bilimleri"]),
    ("CS", ["Computer Science", "Bilgisayar Bilimleri"]),
    ("SE", ["Software Engineering", "Yazılım Mühendisliği"]),
    ("ISE", ["Information Systems Engineering", "Bilişim Sistemleri Mühendisliği"]),
    ("EE", ["Electrical-Electronics Engineering", "Elektrik-Elektronik Mühendisliği", "Electrical Engineering", "Elektrik Mühendisliği"]),
    ("ECE", ["Electronics and Communication Engineering", "Elektronik ve Haberleşme Mühendisliği"]),
    ("ME", ["Mechanical Engineering", "Makine Mühendisliği", "Makina Mühendisliği"]),
    ("MX", ["Mechatronics Engineering", "Mekatronik Mühendisliği"]),
]
match = DegreeMatcher(PROGRAMS).match


@pytest.mark.parametrize("text, expected", [
    ("BSc in Computer Engineering", {"CE"}),
    ("Mechanical Engineering degree", {"ME"}),
    ("Degree in Computer Science", {"CS", "CE"}),
    ("Bilgisayar Bilimleri mezunu", {"CS", "CE"}),
    ("Join our Software Engineering team", set()),
    ("Experience wiring electrical cabinets; degree preferred", set()),
    ("Yazılım Mühendisliği ekibimize katılacak", set()),
    ("BSc in Computer Engineering. You will support the Mechanical Engineering team.", {"CE"}),
    ("M.Sc. or Ph.D. in Mechanical Engineering", {"ME"}),
    ("BSc in Mechanical, Electrical/Electronics or Materials Engineering", {"ME", "EE"}),
    ("Makine veya Mekatronik Mühendisliği lisans mezunu", {"ME", "MX"}),
    ("Student in Mechanical, Electrical/Electronics, Industrial, or Materials Engineering", {"ME", "EE"}),
    ("Degree in a relevant engineering field (Mechanical or Electrical preferred)", set()),  # known miss: no ending
    ("Electrical Engineering degree", {"EE"}),
    ("Degree in Electrical & Electronics Engineering", {"EE"}),
    ("Elektrik-Elektronik Mühendisliği mezunu", {"EE"}),
    ("Electronics and Communication Engineering degree", {"ECE"}),
    ("Elektronik ve Haberleşme Mühendisliği mezunu", {"ECE"}),
    ("Electronics Engineering degree", set()),
    ("degree in Information Systems", set()),
    ("Information Systems Engineering degree", {"ISE"}),
    ("Management Information Systems degree", set()),
    ("Yönetim Bilişim Sistemleri mezunu", set()),
    ("A degree in Software Engineering is a plus", {"SE"}),
    ("degree in a related field", set()),
    ("Engineering degree", set()),
    ("Mechanical Engineering or related field", {"ME"}),
    ("Meslek Lisesi / MYO / Ön Lisans Mekatronik mezunu", set()),
    ("ÖNLİSANS Mekatronik bölümü mezunu", set()),
    ("Meslek Lisesi veya MYO Makine Mühendisliği bölümlerinden mezun", set()),
    ("Önlisans Elektrik Mühendisliği öğrencisi", set()),
    ("Associate degree in Mechatronics Engineering", set()),
    ("Associate or Bachelor's degree in Mechanical Engineering", {"ME"}),
    ("Ön Lisans veya Lisans Makine Mühendisliği mezunu", {"ME"}),
    ("Sales Associate. Degree in Mechanical Engineering", {"ME"}),
    ("MAKİNE MÜHENDİSLİĞİ BÖLÜMÜ MEZUNU", {"ME"}),
    ("Makine Mühendisliği'nden mezun", {"ME"}),
    ("Makine Muhendisligi mezunu", {"ME"}),
    ("Makine, Elektrik veya Mekatronik Mühendisliği bölümlerinden mezun", {"ME", "EE", "MX"}),
    ("A 360-degree view of mechanical engineering", set()),
    ("Requirements\n• Degree in Software Engineering\n• Mechanical Engineering knowledge", {"SE"}),
    ("", set()),
    (None, set()),
])
def test_degree_matcher(text, expected):
    assert match(text) == expected
