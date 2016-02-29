import copy
import six

from django.conf import settings
from django.forms import widgets
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.core.validators import ValidationError
from registration.models import RegistrationProfile
from rest_framework import serializers

from onadata.apps.main.forms import UserProfileForm
from onadata.apps.main.forms import RegistrationFormUserProfile
from onadata.apps.main.models import UserProfile
from onadata.libs.serializers.fields.json_field import JsonField
from onadata.libs.permissions import CAN_VIEW_PROFILE, is_organization


def _get_first_last_names(name, limit=30):
    if not isinstance(name, six.string_types):
        return name, name

    if name.__len__() > (limit * 2):
        # since we are using the default django User Model, there is an
        # imposition of 30 characters on both first_name and last_name hence
        # ensure we only have 30 characters for either field

        return name[:limit], name[limit:limit * 2]

    name_split = name.split()
    first_name = name_split[0]
    last_name = u''

    if len(name_split) > 1:
        last_name = u' '.join(name_split[1:])

    return first_name, last_name


class UserProfileSerializer(serializers.HyperlinkedModelSerializer):
    is_org = serializers.SerializerMethodField('is_organization')
    username = serializers.CharField(source='user.username')
    email = serializers.CharField(source='user.email')
    website = serializers.CharField(source='home_page', required=False)
    gravatar = serializers.ReadOnlyField()
    password = serializers.CharField(
        source='user.password', style={'input_type': 'password'}, required=False)
    user = serializers.HyperlinkedRelatedField(
        view_name='user-detail', lookup_field='username', read_only=True)
    metadata = JsonField(required=False)
    id = serializers.ReadOnlyField(source='user.id')

    class Meta:
        model = UserProfile
        fields = ('id', 'is_org', 'url', 'username', 'name', 'password',
                  'email', 'city', 'country', 'organization', 'website',
                  'twitter', 'gravatar', 'require_auth', 'user', 'metadata')
        lookup_field = 'user'

    def is_organization(self, obj):
        return is_organization(obj)

    def to_representation(self, obj):
        """
        Serialize objects -> primitives.
        """
        ret = super(UserProfileSerializer, self).to_representation(obj)
        if 'password' in ret:
            del ret['password']

        request = self.context['request'] \
            if 'request' in self.context else None

        if 'email' in ret and request is None or request.user \
                and not request.user.has_perm(CAN_VIEW_PROFILE, obj):
            del ret['email']

        return ret

    def create(self, validated_data):
        params = copy.deepcopy(validated_data)
        username = validated_data.get('user.username', None)
        password = validated_data.get('user.password', None)
        email = validated_data.get('user.email', None)

        if username:
            params['username'] = username

        if email:
            params['email'] = email

        if password:
            params.update({'password1': password, 'password2': password})

        form = RegistrationFormUserProfile(params)
        # does not require captcha
        form.REGISTRATION_REQUIRE_CAPTCHA = False

        if form.is_valid():
            site = Site.objects.get(pk=settings.SITE_ID)
            new_user = RegistrationProfile.objects.create_inactive_user(
                site,
                username=username,
                password=password,
                email=email,
                site=site,
                send_email=True)
            new_user.is_active = True
            new_user.save()

            created_by = self.context['request'].user
            created_by = None if created_by.is_anonymous() else created_by
            profile = UserProfile.objects.create(
                user=new_user, name=validated_data.get('name', u''),
                created_by=created_by,
                city=validated_data.get('city', u''),
                country=validated_data.get('country', u''),
                organization=validated_data.get('organization', u''),
                home_page=validated_data.get('home_page', u''),
                twitter=validated_data.get('twitter', u''))

            return profile

        else:
            self.errors.update(form.errors)

        return validated_data

    def update(self, instance, validated_data):

        params = copy.deepcopy(validated_data)
        username = validated_data.get('user.username', None)
        password = validated_data.get('user.password', None)
        name = validated_data.get('name', None)
        email = validated_data.get('user.email', None)

        if username:
            params['username'] = username

        if email:
            params['email'] = email

        if password:
            params.update({'password1': password, 'password2': password})

            form = UserProfileForm(params, instance=instance)

            # form.is_valid affects instance object for partial updates [PATCH]
            # so only use it for full updates [PUT], i.e shallow copy effect
            if not self.partial and form.is_valid():
                instance = form.save()

            # get user
            if email:
                instance.user.email = form.cleaned_data['email']

            if name:
                first_name, last_name = _get_first_last_names(name)
                instance.user.first_name = first_name
                instance.user.last_name = last_name

            if email or name:
                instance.user.save()

        return super(
            UserProfileSerializer, self).create(instance, validated_data)

    def validate_username(self, value):
        if self.context['request'].method == 'PATCH':
            return value

        username = value.lower()
        form = RegistrationFormUserProfile
        if username in form._reserved_usernames:
            raise ValidationError(
                u"%s is a reserved name, please choose another" % username)
        elif not form.legal_usernames_re.search(username):
            raise ValidationError(
                u'username may only contain alpha-numeric characters and '
                u'underscores')
        try:
            User.objects.get(username=username)
        except User.DoesNotExist:

            return value
        raise ValidationError(u'%s already exists' % username)


class UserProfileWithTokenSerializer(UserProfileSerializer):
    username = serializers.CharField(source='user.username')
    email = serializers.CharField(source='user.email')
    website = serializers.CharField(source='home_page', required=False)
    gravatar = serializers.ReadOnlyField()
    password = serializers.CharField(
        source='user.password', style={'input_type': 'password'}, required=False)
    user = serializers.HyperlinkedRelatedField(
        view_name='user-detail', lookup_field='username', read_only=True)
    api_token = serializers.SerializerMethodField('api_token')
    temp_token = serializers.SerializerMethodField('temp_token')

    class Meta:
        model = UserProfile
        fields = ('url', 'username', 'name', 'password', 'email', 'city',
                  'country', 'organization', 'website', 'twitter', 'gravatar',
                  'require_auth', 'user', 'api_token', 'temp_token')
        lookup_field = 'user'

    def get_api_token(self, object):
        return object.user.auth_token.key

    def get_temp_token(self, object):
        request = self.context['request']
        session_key = None
        if request:
            session = request.session
            session_key = session.session_key

        return session_key
