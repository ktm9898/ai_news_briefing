import os
from gws_manager import GWSManager

def check_quota():
    gws = GWSManager()
    drive = gws._get_drive_service()

    about = drive.about().get(fields="storageQuota, user").execute()
    print(f"Service Account Info: {about.get('user', {}).get('emailAddress')}")
    quota = about.get('storageQuota', {})
    limit = int(quota.get('limit', 0))
    usage = int(quota.get('usage', 0))
    usage_drive = int(quota.get('usageInDrive', 0))
    usage_trash = int(quota.get('usageInDriveTrash', 0))

    if limit > 0:
        print(f"Limit: {limit / (1024*1024*1024):.2f} GB")
    else:
        print("Limit: Unlimited or Not Available")
    print(f"Usage: {usage / (1024*1024):.2f} MB")
    print(f"Usage in Drive: {usage_drive / (1024*1024):.2f} MB")
    print(f"Usage in Trash: {usage_trash / (1024*1024):.2f} MB")

    # Try creating a file in root
    try:
        file_metadata = {
            'name': 'Test Root File',
            'mimeType': 'application/vnd.google-apps.document',
        }
        file = drive.files().create(body=file_metadata, fields='id').execute()
        print(f"Created in root successfully! ID: {file.get('id')}")
        drive.files().delete(fileId=file.get('id')).execute()
        print("Deleted successfully from root.")
    except Exception as e:
        print(f"Failed to create in root: {e}")

    # Try creating a file in the shared folder
    from config import GWS_DRIVE_FOLDER_ID
    print(f"Testing in folder: {GWS_DRIVE_FOLDER_ID}")
    try:
        file_metadata = {
            'name': 'Test Folder File',
            'mimeType': 'application/vnd.google-apps.document',
            'parents': [GWS_DRIVE_FOLDER_ID]
        }
        file = drive.files().create(body=file_metadata, fields='id').execute()
        print(f"Created in folder successfully! ID: {file.get('id')}")
        drive.files().delete(fileId=file.get('id')).execute()
        print("Deleted successfully from folder.")
    except Exception as e:
        print(f"Failed to create in folder: {e}")

if __name__ == '__main__':
    check_quota()
