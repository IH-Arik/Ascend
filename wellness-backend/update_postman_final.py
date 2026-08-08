import json

path = r'c:\Users\IH ARIK\Desktop\ARIK\Welldomain\Welldomain_API.postman_collection.json'

with open(path, 'r', encoding='utf-8') as f:
    collection = json.load(f)

def add_or_update(parent_folder_name, new_item):
    # Search top level
    for folder in collection['item']:
        if folder.get('name') == parent_folder_name and 'item' in folder:
            for i, existing in enumerate(folder['item']):
                if existing.get('name') == new_item['name']:
                    folder['item'][i] = new_item
                    return
            folder['item'].append(new_item)
            return
    
    # Search second level
    for folder in collection['item']:
        if 'item' in folder:
            for sub in folder['item']:
                if sub.get('name') == parent_folder_name and 'item' in sub:
                    for i, existing in enumerate(sub['item']):
                        if existing.get('name') == new_item['name']:
                            sub['item'][i] = new_item
                            return
                    sub['item'].append(new_item)
                    return

# LEADER Updates
leader_folder = "Leader Dashboard"
new_leader_items = [
    {
        "name": "Leader Alerts",
        "request": {
            "method": "GET",
            "url": {"raw": "{{base_url}}/dashboard/leader/alerts?department={{department}}&team={{team}}&range=30d", "path": ["dashboard", "leader", "alerts"]}
        }
    },
    {
        "name": "Leader Burnout Recommendations",
        "request": {
            "method": "GET",
            "url": {"raw": "{{base_url}}/dashboard/leader/burnout-recommendations?department={{department}}&team={{team}}&range=30d", "path": ["dashboard", "leader", "burnout-recommendations"]}
        }
    },
    {
        "name": "Leader Burnout Details",
        "request": {
            "method": "GET",
            "url": {"raw": "{{base_url}}/dashboard/leader/burnout-details?department={{department}}&team={{team}}&range=30d", "path": ["dashboard", "leader", "burnout-details"]}
        }
    },
    {
        "name": "Leader OPS Trend",
        "request": {
            "method": "GET",
            "url": {"raw": "{{base_url}}/dashboard/leader/ops-trend?department={{department}}&team={{team}}&range=30d", "path": ["dashboard", "leader", "ops-trend"]}
        }
    }
]

# SUPERADMIN Updates
sa_folder = "Superadmin Dashboard"
new_sa_items = [
    {
        "name": "Superadmin Alerts",
        "request": {
            "method": "GET",
            "url": {"raw": "{{base_url}}/dashboard/superadmin/alerts?company={{organization_name}}&department={{department}}&team={{team}}&range=30d", "path": ["dashboard", "superadmin", "alerts"]}
        }
    },
    {
        "name": "Superadmin Burnout Recommendations",
        "request": {
            "method": "GET",
            "url": {"raw": "{{base_url}}/dashboard/superadmin/burnout-recommendations?company={{organization_name}}&department={{department}}&team={{team}}&range=30d", "path": ["dashboard", "superadmin", "burnout-recommendations"]}
        }
    },
    {
        "name": "Superadmin Burnout Details",
        "request": {
            "method": "GET",
            "url": {"raw": "{{base_url}}/dashboard/superadmin/burnout-details?company={{organization_name}}&department={{department}}&team={{team}}&range=30d", "path": ["dashboard", "superadmin", "burnout-details"]}
        }
    }
]

# Common setup for new items
for item in new_leader_items + new_sa_items:
    item['request']['header'] = [{"key": "Authorization", "value": "Bearer {{access_token}}"}]
    item['request']['url']['host'] = ["{{base_url}}"]

for item in new_leader_items: add_or_update(leader_folder, item)
for item in new_sa_items: add_or_update(sa_folder, item)

# Add Assessment Status
add_or_update("Assessments", {
    "name": "Get Status",
    "request": {
        "method": "GET",
        "header": [{"key": "Authorization", "value": "Bearer {{access_token}}"}],
        "url": {"raw": "{{base_url}}/assessments/status", "host": ["{{base_url}}"], "path": ["assessments", "status"]}
    }
})

with open(path, 'w', encoding='utf-8') as f:
    json.dump(collection, f, indent=2)

print("Collection updated successfully.")
