import pytest

URL = "/api/v1/patients"

NEW_PATIENT = {
    "first_name": "Aarav",
    "last_name": "Ramesh",
    "date_of_birth": "2002-05-14",
    "gender": "male",
    "phone": "+91 98765 43210",
    "address": "12 MG Road, Bengaluru",
}


def create(client, **overrides):
    response = client.post(URL, json={**NEW_PATIENT, **overrides})
    assert response.status_code == 201, response.text
    return response.json()


def test_create_returns_201_with_id_and_computed_fields(client):
    body = create(client)

    assert body["patient_id"] == "PAT-0001"
    assert body["full_name"] == "Aarav Ramesh"
    assert body["phone"] == "+919876543210"
    assert isinstance(body["age"], int)
    assert body["created_at"].endswith("+05:30")  # returned in IST
    assert "_id" not in body


def test_create_with_invalid_data_returns_422_with_field_errors(client):
    response = client.post(URL, json={**NEW_PATIENT, "phone": "123", "gender": "x"})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert {e["field"] for e in body["errors"]} == {"phone", "gender"}


def test_get_patient(client):
    create(client)

    response = client.get(f"{URL}/PAT-0001")

    assert response.status_code == 200
    assert response.json()["first_name"] == "Aarav"
    assert "_id" not in response.json()


def test_get_unknown_patient_returns_404(client):
    response = client.get(f"{URL}/PAT-9999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Patient not found.", "code": "PATIENT_NOT_FOUND"}


def test_list_is_newest_first_with_paging(client):
    for name in ["Aarav", "Priya", "Rahul"]:
        create(client, first_name=name)

    body = client.get(URL, params={"page": 1, "limit": 2}).json()

    assert body["total"] == 3
    assert (body["page"], body["limit"]) == (1, 2)
    assert [p["first_name"] for p in body["items"]] == ["Rahul", "Priya"]
    assert all("_id" not in p for p in body["items"])


def test_list_search(client):
    create(client)
    create(client, first_name="Priya", last_name="Sharma", phone="+918888888888")

    body = client.get(URL, params={"search": "sharma"}).json()

    assert [p["patient_id"] for p in body["items"]] == ["PAT-0002"]


@pytest.mark.parametrize("params", [{"page": 0}, {"limit": 0}, {"limit": 101}])
def test_list_rejects_bad_paging(client, params):
    response = client.get(URL, params=params)

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_update_changes_only_sent_fields(client):
    create(client)

    response = client.put(f"{URL}/PAT-0001", json={"address": "45 Park Street, Kolkata"})

    assert response.status_code == 200
    body = response.json()
    assert body["address"] == "45 Park Street, Kolkata"
    assert body["first_name"] == "Aarav"


def test_update_cannot_change_patient_id(client):
    create(client)

    response = client.put(f"{URL}/PAT-0001", json={"patient_id": "PAT-0050"})

    assert response.status_code == 422
    assert client.get(f"{URL}/PAT-0001").status_code == 200


def test_update_unknown_patient_returns_404(client):
    response = client.put(f"{URL}/PAT-9999", json={"address": "45 Park Street, Kolkata"})

    assert response.status_code == 404
    assert response.json()["code"] == "PATIENT_NOT_FOUND"


def test_list_shows_case_sheet_status_without_clinical_data(client):
    create(client)
    client.put(
        f"{URL}/PAT-0001/case-sheet",
        json={"chief_complaint": {"complaint": "Tooth pain", "duration": None}},
    )

    item = client.get(URL).json()["items"][0]

    assert item["case_sheet_status"] == "pending"
    assert item["case_sheet_updated_at"].endswith("+05:30")
    assert "case_sheet" not in item  # only the flattened status fields
    assert "Tooth pain" not in str(item)


def test_list_sort_by_name_via_api(client):
    create(client, first_name="Zoya")
    create(client, first_name="arjun")

    body = client.get(URL, params={"sort": "name", "order": "asc"}).json()

    assert [p["first_name"] for p in body["items"]] == ["arjun", "Zoya"]


@pytest.mark.parametrize("params", [{"sort": "phone"}, {"order": "up"}])
def test_list_rejects_unknown_sort(client, params):
    response = client.get(URL, params=params)

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
