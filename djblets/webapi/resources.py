from django.conf.urls.defaults import include, patterns, url
from django.core.urlresolvers import reverse
from django.db import models

from djblets.util.misc import never_cache_patterns
from djblets.webapi.core import WebAPIResponse, WebAPIResponseError
from djblets.webapi.decorators import webapi_login_required
from djblets.webapi.errors import WebAPIError


class WebAPIResource(object):
    model = None
    uri_id_key = 'object_id'
    fields = ()
    uris = {}

    allowed_methods = ('GET', 'POST', 'PUT', 'DELETE')

    method_mapping = {
        'GET': 'get',
        'POST': 'create',
        'PUT': 'update',
        'DELETE': 'delete',
    }

    def __call__(self, request, api_format="json", *args, **kwargs):
        method = request.GET.get('method', request.method)

        if method in self.allowed_methods:
            if method == "GET" and self.uri_id_key not in kwargs:
                view = self.get_list
            else:
                view = getattr(self, self.method_mapping.get(method, None))
        else:
            view = None

        if view and callable(view):
            result = view(request, *args, **kwargs)

            if isinstance(result, WebAPIResponse):
                return result
            elif isinstance(result, WebAPIError):
                return WebAPIResponseError(request, err=result,
                                           api_format=api_format)
            elif isinstance(result, tuple):
                if isinstance(result[0], WebAPIError):
                    return WebAPIResponseError(request,
                                               err=result[0],
                                               obj=result[1],
                                               api_format=api_format)
                else:
                    return WebAPIResponse(request,
                                          status=result[0],
                                          obj=result[1],
                                          api_format=api_format)
        else:
            return HttpResponseNotAllowed(self.allowed_methods)

    @property
    def __name__(self):
        return self.__class__.__name__

    @property
    def name(self):
        if self.model:
            return self.model.__name__.lower()
        else:
            return self.__name__.lower()

    @property
    def name_plural(self):
        return self.name + 's'

    def get(self, request, *args, **kwargs):
        if not self.model:
            return HttpResponseNotAllowed(self.allowed_methods)

        try:
            queryset = self.get_queryset(request, *args, **kwargs)
            obj = queryset.get(pk=kwargs[self.uri_id_key])
        except self.model.DoesNotExist:
            return DOES_NOT_EXIST

        if not self.has_access_permissions(request, obj, *args, **kwargs):
            return PERMISSION_DENIED

        return 200, {
            self.name: self.serialize_object(obj, *args, **kwargs),
        }

    def get_list(self, request, *args, **kwargs):
        if not self.model:
            return HttpResponseNotAllowed(self.allowed_methods)

        # TODO: Paginate this.
        return 200, {
            self.name_plural: self.get_queryset(request, is_list=True,
                                                *args, **kwargs),
        }

    @webapi_login_required
    def create(self, request, api_format, *args, **kwargs):
        return HttpResponseNotAllowed(self.allowed_methods)

    @webapi_login_required
    def update(self, request, api_format, *args, **kwargs):
        return HttpResponseNotAllowed(self.allowed_methods)

    @webapi_login_required
    def delete(self, request, api_format, *args, **kwargs):
        if not self.model:
            return HttpResponseNotAllowed(self.allowed_methods)

        try:
            queryset = self.get_queryset(request, *args, **kwargs)
            obj = queryset.filter(pk=kwargs[self.uri_id_key])
        except self.model.DoesNotExist:
            return DOES_NOT_EXIST

        if not self.has_delete_permissions(request, obj, *args, **kwargs):
            return PERMISSION_DENIED

        obj.delete()

        return 204, {}

    def get_queryset(self, request, *args, **kwargs):
        return self.model.all()

    def get_url_patterns(self):
        if not self.uri_id_key:
            return patterns('')

        item_regex = r'^(?P<%s>[0-9]+)/$' % self.uri_id_key

        return never_cache_patterns('',
            url(r'^$', self, name='%s-resource' % self.name_plural),
            url(item_regex, self, name='%s-resource' % self.name),
        )

    def has_access_permissions(self, request, obj, *args, **kwargs):
        return True

    def has_delete_permissions(self, request, obj, *args, **kwargs):
        return True

    def serialize_object(self, obj, api_format='json', *args, **kwargs):
        data = {
            'href': reverse('%s-resource' % self.name,
                            kwargs={
                                'api_format': api_format,
                                self.uri_id_key: obj.id
                            })
        }

        for field in self.fields:
            serialize_func = getattr(self, "serialize_%s_field" % field, None)

            if serialize_func and callable(serialize_func):
                value = serialize_func(obj)
            else:
                value = getattr(obj, field)

                if isinstance(value, models.ManyToManyField):
                    value = value.all()
                elif isinstance(value, models.ForeignKey):
                    value = value.get()

            data[field] = value

        return data
