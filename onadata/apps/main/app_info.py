import json
import os
from django.http.response import HttpResponseNotFound, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from django.conf import settings

@csrf_exempt
def app_info(request):
    if request.method == 'GET':
        package_info = {}
        try:
            package_dir = os.path.abspath(os.path.join(settings.BASE_DIR, os.pardir))
            config_file = os.path.join(package_dir, 'package.json')
            with open(config_file, "r") as f:
                package_info = json.loads(f.read())
        except IOError:
            return HttpResponseNotFound()
        
        data = {
            "name": package_info["name"],
            "description": package_info["description"],
            "version": package_info["version"]
        }

        return JsonResponse(data)
