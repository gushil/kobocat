from django.contrib.auth.models import User
from django.core.validators import ValidationError
from rest_framework import serializers

from onadata.apps.api import tools
from onadata.apps.api.models import OrganizationProfile
from onadata.apps.api.tools import get_organization_members
from onadata.apps.main.forms import RegistrationFormUserProfile
from onadata.libs.permissions import get_role_in_org


class OrganizationSerializer(serializers.HyperlinkedModelSerializer):
    org = serializers.CharField(source='user.username')
    user = serializers.HyperlinkedRelatedField(
        view_name='user-detail', lookup_field='username', read_only=True)
    creator = serializers.HyperlinkedRelatedField(
        view_name='user-detail', lookup_field='username', read_only=True)
    users = serializers.SerializerMethodField('get_org_permissions')

    class Meta:
        model = OrganizationProfile
        exclude = ('created_by', 'is_organization', 'organization')
        extra_kwargs = {
            'url': {'lookup_field': 'user'}
        }

    def create(self, validated_data):
        # get('user.username') does not work anymore:
        # username is in a nested dict
        org = validated_data.get('user', {}).get('username', None)
        org_name = validated_data.get('name', None)
        org_exists = False
        creator = None

        try:
            User.objects.get(username=org)
        except User.DoesNotExist:
            pass
        else:
            self.errors['org'] = u'Organization %s already exists.' % org
            org_exists = True

        if 'request' in self.context:
            creator = self.context['request'].user

        if org and org_name and creator and not org_exists:
            validated_data['organization'] = org_name
            orgprofile = tools.create_organization_object(org, creator, validated_data)
            orgprofile.save()
            return orgprofile

        if not org:
            self.errors['org'] = u'org is required!'

        if not org_name:
            self.errors['name'] = u'name is required!'

        return validated_data

    def validate_org(self, value):
        org = value.lower()
        if org in RegistrationFormUserProfile._reserved_usernames:
            raise ValidationError(
                u"%s is a reserved name, please choose another" % org)
        elif not RegistrationFormUserProfile.legal_usernames_re.search(org):
            raise ValidationError(
                u'organization may only contain alpha-numeric characters and '
                u'underscores')
        try:
            User.objects.get(username=org)
        except User.DoesNotExist:
            return value
        raise ValidationError(u'%s already exists' % org)

    def get_org_permissions(self, obj):
        members = get_organization_members(obj) if obj else []

        return [{
            'user': u.username,
            'role': get_role_in_org(u, obj)
        } for u in members]
