from django.contrib import admin
from django.contrib.sites.shortcuts import get_current_site
from django.urls import reverse
from django.utils.translation import ugettext_lazy as _
from django.utils.html import mark_safe
from django.contrib.admin import widgets

from .models import Meeting
from .forms import (
    MeetingForm,
    MEETING_MAIN_FIELDS,
    MEETING_DATE_FIELDS,
    MEETING_RECURRING_FIELDS,
    get_meeting_fields,
)


class MeetingSuperAdminForm(MeetingForm):
    is_staff = True
    is_superuser = True
    is_admin = True
    admin_form = True

    class Meta(object):
        model = Meeting
        fields = "__all__"
        widgets = {
            "owner": widgets.AutocompleteSelect(
                Meeting._meta.get_field("owner"),
                admin.site,
                attrs={"style": "width: 20em"},
            ),
            "additional_owners": widgets.AutocompleteSelectMultiple(
                Meeting._meta.get_field("additional_owners"),
                admin.site,
                attrs={"style": "width: 20em"},
            ),
            "restrict_access_to_groups": widgets.AutocompleteSelectMultiple(
                Meeting._meta.get_field("restrict_access_to_groups"),
                admin.site,
                attrs={"style": "width: 20em"},
            ),
            "start": widgets.AdminDateWidget(),
            "recurring_until": widgets.AdminDateWidget(),
        }


class MeetingAdminForm(MeetingForm):
    is_staff = True
    is_superuser = False
    is_admin = True
    admin_form = True

    class Meta(object):
        model = Meeting
        fields = "__all__"
        widgets = {
            "owner": widgets.AutocompleteSelect(
                Meeting._meta.get_field("owner"),
                admin.site,
                attrs={"style": "width: 20em"},
            ),
            "additional_owners": widgets.AutocompleteSelectMultiple(
                Meeting._meta.get_field("additional_owners"),
                admin.site,
                attrs={"style": "width: 20em"},
            ),
            "restrict_access_to_groups": widgets.AutocompleteSelectMultiple(
                Meeting._meta.get_field("restrict_access_to_groups"),
                admin.site,
                attrs={"style": "width: 20em"},
            ),
            "start": widgets.AdminDateWidget(),
            "recurring_until": widgets.AdminDateWidget(),
        }


class IsPaidFilter(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = "is active"

    # Parameter for the filter that will be used in the URL query.
    parameter_name = "is_active"

    def lookups(self, request, model_admin):
        return (("1", _("Yes")), ("0", _("No")))

    def queryset(self, request, queryset):
        if self.value() == "1":
            meetings = [meeting.id for meeting in (queryset) if meeting.is_active]
            return queryset.filter(id__in=meetings)
        else:
            return queryset


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    date_hierarchy = "updated_at"
    search_fields = ["name", "meeting_id"]
    list_display = (
        "name",
        "owner",
        "meeting_id",
        "created_at",
        "start_at",
        "is_active",
        "is_running",
        "join_url",  # , 'meeting_actions'
    )

    @admin.display(empty_value="")
    def join_url(self, obj):
        direct_join_url = reverse(
            "meeting:join", args=(obj.meeting_id, obj.get_hashkey())
        )
        link = '<a href="%s" target="_blank">%s</a>' % (direct_join_url, _("join"))
        return mark_safe(link)

    list_filter = ("start_at", "is_running", IsPaidFilter)
    # actions = ["update_running_meetings"] if not UPDATE_RUNNING_ON_EACH_CALL else []
    list_per_page = 30
    autocomplete_fields = [
        "owner",
        "additional_owners",
        "restrict_access_to_groups",
    ]
    readonly_fields = ("meeting_id",)
    list_display_links = ("name",)

    fieldsets = (
        (None, {"fields": MEETING_MAIN_FIELDS}),
        (_("Date"), {"fields": MEETING_DATE_FIELDS}),
        (_("Recurring"), {"fields": MEETING_RECURRING_FIELDS}),
        (
            "Advanced options",
            {
                "classes": ("collapse",),
                "fields": get_meeting_fields(),
            },
        ),
    )

    # form = MeetingForm
    def get_form(self, request, obj=None, **kwargs):
        if request.user.is_superuser:
            form = MeetingSuperAdminForm
        else:
            form = MeetingAdminForm
        # form = super(MeetingAdmin, self).get_form(request, obj, **kwargs)
        return form

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            qs = qs.filter(site=get_current_site(request))
        return qs
