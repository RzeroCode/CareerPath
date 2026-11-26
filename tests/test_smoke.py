import pytest


@pytest.mark.django_db
def test_home_page_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"2021 dataset" in response.content  # the old query screen must say its data is out of date


@pytest.mark.django_db
def test_admin_login_page_renders(client):
    assert client.get("/admin/login/").status_code == 200
