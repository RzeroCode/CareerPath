import pytest


@pytest.mark.django_db
def test_home_page_renders(client):
    assert client.get("/").status_code == 200


@pytest.mark.django_db
def test_admin_login_page_renders(client):
    assert client.get("/admin/login/").status_code == 200
