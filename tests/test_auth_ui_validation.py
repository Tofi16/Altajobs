def test_username_check_endpoint_reports_availability(client):
    response = client.get('/api/check-username?username=unique_username_12345')
    assert response.status_code == 200
    data = response.get_json()
    assert data['available'] is True
