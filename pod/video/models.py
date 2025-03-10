"""Esup-Pod Video models."""

import os
import re
import time
import unicodedata
import json
import logging
import hashlib
import datetime

from django.db import models
from django.conf import settings
from django.utils.translation import ugettext_lazy as _
from django.utils.translation import get_language
from django.template.defaultfilters import slugify
from django.db.models import Sum
from django.contrib.auth.models import User
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.core.exceptions import ObjectDoesNotExist
from django.core.validators import MaxValueValidator
from django.contrib.sites.shortcuts import get_current_site
from django.templatetags.static import static
from django.dispatch import receiver
from django.utils.html import format_html
from django.db.models.signals import pre_delete
from tagging.models import Tag
from datetime import date
from django.utils import timezone
from ckeditor.fields import RichTextField
from tagging.fields import TagField
from django.utils.text import capfirst
from django.contrib.sites.models import Site
from django.db.models.signals import post_save
from django.db.models.signals import pre_save
from pod.main.models import AdditionalChannelTab
import importlib

from sorl.thumbnail import get_thumbnail
from pod.authentication.models import AccessGroup
from pod.main.models import get_nextautoincrement
from pod.main.lang_settings import ALL_LANG_CHOICES, PREF_LANG_CHOICES
from django.db.models import Count, Case, When, Value, BooleanField, Q
from django.db.models.functions import Concat
from os.path import splitext

if getattr(settings, "USE_PODFILE", False):
    from pod.podfile.models import CustomImageModel

    FILEPICKER = True
else:
    FILEPICKER = False
    from pod.main.models import CustomImageModel

logger = logging.getLogger(__name__)

RESTRICT_EDIT_VIDEO_ACCESS_TO_STAFF_ONLY = getattr(
    settings, "RESTRICT_EDIT_VIDEO_ACCESS_TO_STAFF_ONLY", False
)
VIDEO_RECENT_VIEWCOUNT = getattr(settings, "VIDEO_RECENT_VIEWCOUNT", 180)
VIDEOS_DIR = getattr(settings, "VIDEOS_DIR", "videos")
SITE_ID = getattr(settings, "SITE_ID", 1)

LANG_CHOICES = getattr(
    settings,
    "LANG_CHOICES",
    ((" ", PREF_LANG_CHOICES), ("----------", ALL_LANG_CHOICES)),
)

CURSUS_CODES = getattr(
    settings,
    "CURSUS_CODES",
    (
        ("0", _("None / All")),
        ("L", _("Bachelor’s Degree")),
        ("M", _("Master’s Degree")),
        ("D", _("Doctorate")),
        ("1", _("Other")),
    ),
)

LANG_CHOICES_DICT = {key: value for key, value in LANG_CHOICES[0][1] + LANG_CHOICES[1][1]}
CURSUS_CODES_DICT = {key: value for key, value in CURSUS_CODES}

DEFAULT_TYPE_ID = getattr(settings, "DEFAULT_TYPE_ID", 1)
LICENCE_CHOICES = getattr(
    settings,
    "LICENCE_CHOICES",
    (
        ("by", _("Attribution 4.0 International (CC BY 4.0)")),
        (
            "by-nd",
            _("Attribution-NoDerivatives 4.0 International (CC BY-ND 4.0)"),
        ),
        (
            "by-nc-nd",
            _(
                "Attribution-NonCommercial-NoDerivatives 4.0 "
                "International (CC BY-NC-ND 4.0)"
            ),
        ),
        (
            "by-nc",
            _("Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)"),
        ),
        (
            "by-nc-sa",
            _(
                "Attribution-NonCommercial-ShareAlike 4.0 "
                "International (CC BY-NC-SA 4.0)"
            ),
        ),
        ("by-sa", _("Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)")),
    ),
)
LICENCE_CHOICES_DICT = {key: value for key, value in LICENCE_CHOICES}
FORMAT_CHOICES = getattr(
    settings,
    "FORMAT_CHOICES",
    (
        ("video/mp4", "video/mp4"),
        ("video/mp2t", "video/mp2t"),
        ("video/webm", "video/webm"),
        ("audio/mp3", "audio/mp3"),
        ("audio/wav", "audio/wav"),
        ("application/x-mpegURL", "application/x-mpegURL"),
    ),
)
ENCODING_CHOICES = getattr(
    settings,
    "ENCODING_CHOICES",
    (
        ("audio", "audio"),
        ("360p", "360p"),
        ("480p", "480p"),
        ("720p", "720p"),
        ("1080p", "1080p"),
        ("playlist", "playlist"),
    ),
)
DEFAULT_THUMBNAIL = getattr(settings, "DEFAULT_THUMBNAIL", "img/default.svg")
SECRET_KEY = getattr(settings, "SECRET_KEY", "")

NOTES_STATUS = getattr(
    settings,
    "NOTES_STATUS",
    (
        ("0", _("Private (me only)")),
        ("1", _("Shared with video owner")),
        ("2", _("Public")),
    ),
)

THIRD_PARTY_APPS = getattr(settings, "THIRD_PARTY_APPS", [])

THIRD_PARTY_APPS_CHOICES = THIRD_PARTY_APPS.copy()
THIRD_PARTY_APPS_CHOICES.remove("live") if (
    "live" in THIRD_PARTY_APPS_CHOICES
) else THIRD_PARTY_APPS_CHOICES
THIRD_PARTY_APPS_CHOICES.insert(0, "Original")

VERSION_CHOICES = [
    (app.capitalize()[0], _("%(app)s version" % {"app": app.capitalize()}))
    for app in THIRD_PARTY_APPS_CHOICES
]

VERSION_CHOICES_DICT = {key: value for key, value in VERSION_CHOICES}

##
# Settings exposed in templates
#
TEMPLATE_VISIBLE_SETTINGS = getattr(
    settings,
    "TEMPLATE_VISIBLE_SETTINGS",
    {
        "TITLE_SITE": "Pod",
        "TITLE_ETB": "University name",
        "LOGO_SITE": "img/logoPod.svg",
        "LOGO_ETB": "img/logo_etb.svg",
        "LOGO_PLAYER": "img/pod_favicon.svg",
        "LINK_PLAYER": "",
        "FOOTER_TEXT": ("",),
        "FAVICON": "img/pod_favicon.svg",
        "CSS_OVERRIDE": "",
        "PRE_HEADER_TEMPLATE": "",
        "POST_FOOTER_TEMPLATE": "",
        "TRACKING_TEMPLATE": "",
    },
)
TITLE_ETB = (
    TEMPLATE_VISIBLE_SETTINGS["TITLE_ETB"]
    if (TEMPLATE_VISIBLE_SETTINGS.get("TITLE_ETB"))
    else "University name"
)
DEFAULT_DC_COVERAGE = getattr(
    settings, "DEFAULT_DC_COVERAGE", TITLE_ETB + " - Town - Country"
)
DEFAULT_DC_RIGHTS = getattr(settings, "DEFAULT_DC_RIGHT", "BY-NC-SA")

DEFAULT_YEAR_DATE_DELETE = getattr(settings, "DEFAULT_YEAR_DATE_DELETE", 2)


# FUNCTIONS


def default_date_delete():
    return date(
        date.today().year + DEFAULT_YEAR_DATE_DELETE,
        date.today().month,
        date.today().day,
    )


def select_video_owner():
    if RESTRICT_EDIT_VIDEO_ACCESS_TO_STAFF_ONLY:
        return lambda q: (
            Q(is_staff=True) & (Q(first_name__icontains=q) | Q(last_name__icontains=q))
        ) & Q(owner__sites=Site.objects.get_current())
    else:
        return lambda q: (Q(first_name__icontains=q) | Q(last_name__icontains=q)) & Q(
            owner__sites=Site.objects.get_current()
        )


def remove_accents(input_str):
    """Remove diacritics in input string."""
    nkfd_form = unicodedata.normalize("NFKD", input_str)
    return "".join([c for c in nkfd_form if not unicodedata.combining(c)])


def get_storage_path_video(instance, filename):
    """Get the video storage path.

    Instance needs to implement owner
    """
    fname, dot, extension = filename.rpartition(".")
    try:
        fname.index("/")
        return os.path.join(
            VIDEOS_DIR,
            instance.owner.owner.hashkey,
            "%s/%s.%s"
            % (
                os.path.dirname(fname),
                slugify(os.path.basename(fname)),
                extension,
            ),
        )
    except ValueError:
        return os.path.join(
            VIDEOS_DIR,
            instance.owner.owner.hashkey,
            "%s.%s" % (slugify(fname), extension),
        )


# MODELS


class Channel(models.Model):
    """Class describing Channels objects."""

    title = models.CharField(
        _("Title"),
        max_length=100,
        unique=True,
        help_text=_(
            "Please choose a title as short and accurate as "
            "possible, reflecting the main subject / context "
            "of the content.(max length: 100 characters)"
        ),
    )
    slug = models.SlugField(
        _("Slug"),
        unique=True,
        max_length=100,
        help_text=_(
            'Used to access this instance, the "slug" is a short label '
            + "containing only letters, numbers, underscore or dash top."
        ),
        editable=False,
    )
    description = RichTextField(
        _("Description"),
        config_name="complete",
        blank=True,
        help_text=_(
            "In this field you can describe your content, "
            "add all needed related information, and "
            "format the result using the toolbar."
        ),
    )
    headband = models.ForeignKey(
        CustomImageModel,
        models.SET_NULL,
        blank=True,
        null=True,
        verbose_name=_("Headband"),
    )
    color = models.CharField(
        _("Background color"),
        max_length=10,
        blank=True,
        null=True,
        help_text=_(
            "The background color for your channel. "
            "You can use the format #. i.e.: #ff0000 for red"
        ),
    )
    style = models.TextField(
        _("Extra style"),
        null=True,
        blank=True,
        help_text=_("The style will be added to your channel to show it"),
    )
    owners = models.ManyToManyField(
        User,
        related_name="owners_channels",
        verbose_name=_("Owners"),
        blank=True,
    )
    users = models.ManyToManyField(
        User,
        related_name="users_channels",
        verbose_name=_("Users"),
        blank=True,
    )
    visible = models.BooleanField(
        verbose_name=_("Visible"),
        help_text=_(
            "If checked, the channel appear in a list of available "
            + "channels on the platform."
        ),
        default=False,
    )
    allow_to_groups = models.ManyToManyField(
        AccessGroup,
        blank=True,
        verbose_name=_("Groups"),
        help_text=_("Select one or more groups who can upload video to this channel."),
    )
    add_channels_tab = models.ManyToManyField(
        AdditionalChannelTab, verbose_name=_("Additionals channels tab"), blank=True
    )
    site = models.ForeignKey(
        Site, verbose_name=_("Site"), on_delete=models.CASCADE, default=SITE_ID
    )

    class Meta:
        """Metadata subclass for Channel object."""

        ordering = ["title"]
        verbose_name = _("Channel")
        verbose_name_plural = _("Channels")
        constraints = [
            models.UniqueConstraint(
                fields=["slug", "site"], name="channel_unique_slug_site"
            )
        ]

    def __str__(self):
        """Display a channel object as string."""
        return "%s" % (self.title)

    def get_absolute_url(self):
        """Return channel absolute URL."""
        return reverse("channel-video:channel", args=[str(self.slug)])

    def get_all_theme(self):
        """Return the list of all child themes in current channel."""
        list_theme = []
        themes = self.themes.filter(parentId=None).order_by("title")
        for theme in themes:
            list_theme.append(
                {
                    "id": theme.id,
                    "title": "%s" % theme.title,
                    "slug": "%s" % theme.slug,
                    "url": "%s" % theme.get_absolute_url(),
                    "child": theme.get_all_children_tree(),
                }
            )
        return list_theme

    def get_all_theme_json(self):
        """Return theme list in json format."""
        return json.dumps(self.get_all_theme())

    def save(self, *args, **kwargs):
        """Store the channel object in db."""
        self.slug = slugify(self.title)
        super(Channel, self).save(*args, **kwargs)


@receiver(pre_save, sender=Channel)
def default_site_channel(sender, instance, **kwargs):
    if not hasattr(instance, "site"):
        instance.site = Site.objects.get_current()


class Theme(models.Model):
    """Class describing a them object.

    A theme is a child of channel or another theme object.
    """

    parentId = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="children",
        on_delete=models.CASCADE,
        verbose_name=_("Theme parent"),
    )
    title = models.CharField(
        _("Title"),
        max_length=100,
        help_text=_(
            "Please choose a title as short and accurate as "
            "possible, reflecting the main subject / context "
            "of the content.(max length: 100 characters)"
        ),
    )
    slug = models.SlugField(
        _("Slug"),
        max_length=100,
        help_text=_(
            'Used to access this instance, the "slug" is a short label '
            + "containing only letters, numbers, underscore or dash top."
        ),
        editable=False,
    )
    description = models.TextField(
        _("Description"),
        null=True,
        blank=True,
        help_text=_(
            "In this field you can describe your content, "
            "add all needed related information, and "
            "format the result using the toolbar."
        ),
    )

    headband = models.ForeignKey(
        CustomImageModel,
        models.SET_NULL,
        blank=True,
        null=True,
        verbose_name=_("Headband"),
    )

    channel = models.ForeignKey(
        "Channel",
        related_name="themes",
        verbose_name=_("Channel"),
        on_delete=models.CASCADE,
    )

    @property
    def site(self):
        """Return sites associated to parent channel."""
        return self.channel.site

    def __str__(self):
        """Display current theme as string."""
        return "%s: %s" % (self.channel.title, self.title)

    def get_absolute_url(self):
        """Get current theme absolute URL."""
        return reverse(
            "channel-video:theme", args=[str(self.channel.slug), str(self.slug)]
        )

    def save(self, *args, **kwargs):
        """Store current theme object in db."""
        self.slug = slugify(self.title)
        super(Theme, self).save(*args, **kwargs)

    def get_all_children_tree(self):
        """Get a tree of all theme children."""
        children = []
        try:
            child_list = self.children.all().order_by("title")
        except AttributeError:
            return children
        for child in child_list:
            children.append(
                {
                    "id": child.id,
                    "title": "%s" % child.title,
                    "slug": "%s" % child.slug,
                    "url": "%s" % child.get_absolute_url(),
                    "child": child.get_all_children_tree(),
                }
            )
        return children

    def get_all_children_flat(self):
        """Get a flat list of all theme children."""
        children = [self]
        try:
            child_list = self.children.all()
        except AttributeError:
            return children
        for child in child_list:
            children.extend(child.get_all_children_flat())
        return children

    def get_all_children_tree_json(self):
        """Get a json tree of all theme children."""
        return json.dumps(self.get_all_children_tree())

    def get_all_parents(self):
        """Get a list of all theme parents."""
        parents = [self]
        if self.parentId is not None:
            parent = self.parentId
            parents.extend(parent.get_all_parents())
        return parents

    def clean(self):
        # Dans le cas où on modifie un theme
        if (
            Theme.objects.filter(channel=self.channel, slug=slugify(self.title))
            .exclude(pk=self.id)
            .exists()
        ):
            raise ValidationError(
                "A theme with this name\
                    already exists in this channel."
            )

        if self.parentId in self.get_all_children_flat():
            raise ValidationError(
                "A theme cannot have itself \
                    or one of it's children as parent."
            )
        if self.parentId and self.parentId not in self.channel.themes.all():
            raise ValidationError(
                "A theme have to be in the same channel that his parent"
            )

    class Meta:
        """Metadata subclass of theme object."""

        ordering = ["channel", "title"]
        verbose_name = _("Theme")
        verbose_name_plural = _("Themes")
        unique_together = ("channel", "slug")


class Type(models.Model):
    """Define all video types available."""

    title = models.CharField(_("Title"), max_length=100, unique=True)
    slug = models.SlugField(
        _("Slug"),
        unique=True,
        max_length=100,
        help_text=_(
            'Used to access this instance, the "slug" is a short label '
            + "containing only letters, numbers, underscore or dash top."
        ),
    )
    description = models.TextField(null=True, blank=True)
    icon = models.ForeignKey(
        CustomImageModel,
        models.SET_NULL,
        blank=True,
        null=True,
        verbose_name=_("Icon"),
    )
    sites = models.ManyToManyField(Site)

    def __str__(self):
        return "%s" % (self.title)

    def save(self, *args, **kwargs):
        """Store current Type in DB."""
        self.slug = slugify(self.title)
        super(Type, self).save(*args, **kwargs)

    class Meta:
        ordering = ["title"]
        verbose_name = _("Type")
        verbose_name_plural = _("Types")


@receiver(post_save, sender=Type)
def default_site_type(sender, instance, created, **kwargs):
    if len(instance.sites.all()) == 0:
        instance.sites.add(Site.objects.get_current())


class Discipline(models.Model):
    title = models.CharField(_("title"), max_length=100, unique=True)
    slug = models.SlugField(
        _("slug"),
        unique=True,
        max_length=100,
        help_text=_(
            'Used to access this instance, the "slug" is a short label '
            + "containing only letters, numbers, underscore or dash top."
        ),
    )
    description = models.TextField(null=True, blank=True)
    icon = models.ForeignKey(
        CustomImageModel,
        models.SET_NULL,
        blank=True,
        null=True,
        verbose_name=_("Icon"),
    )
    site = models.ForeignKey(
        Site, verbose_name=_("Site"), on_delete=models.CASCADE, default=SITE_ID
    )

    def __str__(self):
        return "%s" % (self.title)

    def save(self, *args, **kwargs):
        """Store current Discipline in DB."""
        self.slug = slugify(self.title)
        super(Discipline, self).save(*args, **kwargs)

    class Meta:
        ordering = ["title"]
        verbose_name = _("Discipline")
        verbose_name_plural = _("Disciplines")


@receiver(pre_save, sender=Discipline)
def default_site_discipline(sender, instance, **kwargs):
    if not hasattr(instance, "site"):
        instance.site = Site.objects.get_current()


class Video(models.Model):
    """Class describing video objects."""

    video = models.FileField(
        _("Video"),
        upload_to=get_storage_path_video,
        max_length=255,
        help_text=_("You can send an audio or video file."),
    )
    title = models.CharField(
        _("Title"),
        max_length=250,
        help_text=_(
            "Please choose a title as short and accurate as "
            "possible, reflecting the main subject / context "
            "of the content. (max length: 250 characters)"
        ),
    )
    slug = models.SlugField(
        _("Slug"),
        unique=True,
        max_length=255,
        help_text=_(
            'Used to access this instance, the "slug" is '
            "a short label containing only letters, "
            "numbers, underscore or dash top."
        ),
        editable=False,
    )
    sites = models.ManyToManyField(Site)
    type = models.ForeignKey(
        Type,
        verbose_name=_("Type"),
        on_delete=models.CASCADE,
        help_text=_("Select the general type of the video."),
    )
    owner = models.ForeignKey(User, verbose_name=_("Owner"), on_delete=models.CASCADE)
    additional_owners = models.ManyToManyField(
        User,
        blank=True,
        verbose_name=_("Additional owners"),
        related_name="owners_videos",
        help_text=_(
            "You can add additional owners to the video. "
            + "They will have the same rights as you except "
            + "that they can't delete this video."
        ),
    )
    description = RichTextField(
        _("Description"),
        config_name="complete",
        blank=True,
        help_text=_(
            "In this field you can describe your content, "
            + "add all needed related information, "
            + "and format the result using the toolbar."
        ),
    )
    date_added = models.DateTimeField(_("Date added"), default=timezone.now)
    date_evt = models.DateField(
        _("Date of event"), default=date.today, blank=True, null=True
    )
    cursus = models.CharField(
        _("University course"),
        max_length=1,
        choices=CURSUS_CODES,
        default="0",
        help_text=_("Select an university course as audience target of the content."),
    )
    main_lang = models.CharField(
        _("Main language"),
        max_length=2,
        choices=LANG_CHOICES,
        default=get_language(),
        help_text=_("Select the main language used in the content."),
    )
    transcript = models.BooleanField(
        _("Transcript"),
        default=False,
        help_text=_(
            "Check this box if you want to transcript the audio." "(beta version)"
        ),
    )
    tags = TagField(
        help_text=_(
            "Separate tags with spaces, "
            "enclose the tags consist of several words in quotation marks."
        ),
        verbose_name=_("Tags"),
    )
    discipline = models.ManyToManyField(
        Discipline, blank=True, verbose_name=_("Disciplines")
    )
    licence = models.CharField(
        _("Licence"), max_length=8, choices=LICENCE_CHOICES, blank=True, null=True
    )
    channel = models.ManyToManyField(Channel, verbose_name=_("Channels"), blank=True)
    theme = models.ManyToManyField(
        Theme,
        verbose_name=_("Themes"),
        blank=True,
        help_text=_(
            'Hold down "Control", or "Command" ' "on a Mac, to select more than one."
        ),
    )
    allow_downloading = models.BooleanField(
        _("allow downloading"),
        default=False,
        help_text=_("Check this box if you to allow downloading of the encoded files"),
    )
    is_360 = models.BooleanField(
        _("video 360"),
        default=False,
        help_text=_("Check this box if you want to use the 360 player for the video"),
    )

    is_draft = models.BooleanField(
        verbose_name=_("Draft"),
        help_text=_(
            "If this box is checked, "
            "the video will be visible and accessible only by you "
            "and the additional owners."
        ),
        default=True,
    )
    is_restricted = models.BooleanField(
        verbose_name=_("Restricted access"),
        help_text=_(
            "If this box is checked, "
            "the video will only be accessible to authenticated users."
        ),
        default=False,
    )
    restrict_access_to_groups = models.ManyToManyField(
        AccessGroup,
        blank=True,
        verbose_name=_("Groups"),
        help_text=_("Select one or more groups who can access to this video"),
    )
    password = models.CharField(
        _("password"),
        help_text=_("Viewing this video will not be possible without this password."),
        max_length=50,
        blank=True,
        null=True,
    )

    thumbnail = models.ForeignKey(
        CustomImageModel,
        models.SET_NULL,
        blank=True,
        null=True,
        verbose_name=_("Thumbnails"),
    )
    duration = models.IntegerField(_("Duration"), default=0, editable=False, blank=True)
    overview = models.ImageField(
        _("Overview"),
        null=True,
        upload_to=get_storage_path_video,
        blank=True,
        max_length=255,
        editable=False,
    )

    encoding_in_progress = models.BooleanField(
        _("Encoding in progress"), default=False, editable=False
    )
    is_video = models.BooleanField(_("Is Video"), default=True, editable=False)

    date_delete = models.DateField(_("Date to delete"), default=default_date_delete)

    disable_comment = models.BooleanField(
        _("Disable comment"),
        help_text=_("Allows you to turn off all comments on this video."),
        default=False,
    )

    class Meta:
        """Metadata subclass for Video object."""

        ordering = ["-date_added", "-id"]
        get_latest_by = "date_added"
        verbose_name = _("video")
        verbose_name_plural = _("videos")

    def save(self, *args, **kwargs):
        """Store a video object in db."""
        newid = -1
        if not self.id:
            try:
                newid = get_nextautoincrement(Video)
            except Exception:
                try:
                    newid = Video.objects.latest("id").id
                    newid += 1
                except Exception:
                    newid = 1
            # fix date_delete depends of owner affiliation
            ACCOMMODATION_YEARS = getattr(settings, "ACCOMMODATION_YEARS", {})
            if ACCOMMODATION_YEARS.get(self.owner.owner.affiliation):
                new_year = ACCOMMODATION_YEARS[self.owner.owner.affiliation]
                self.date_delete = date(
                    date.today().year + new_year,
                    date.today().month,
                    date.today().day,
                )
        else:
            newid = self.id
        newid = "%04d" % newid
        self.slug = "%s-%s" % (newid, slugify(self.title))
        self.tags = remove_accents(self.tags)
        super(Video, self).save(*args, **kwargs)

    def __str__(self):
        """Display a video object as string."""
        if self.id:
            return "%s - %s" % ("%04d" % self.id, self.title)
        else:
            return "None"

    @property
    def establishment(self):
        return self.owner.owner.establishment

    @property
    def viewcount(self):
        """Get the view counter of a video."""
        return self.get_viewcount()

    viewcount.fget.short_description = _("Sum of view")

    @property
    def recentViewcount(self):
        """Get the view counter of a video."""
        return self.get_viewcount(VIDEO_RECENT_VIEWCOUNT)

    recentViewcount.fget.short_description = _("Sum of view of last 6 months (180 days)")

    def is_editable(self, user):
        """Return true if video is editable by user."""
        if RESTRICT_EDIT_VIDEO_ACCESS_TO_STAFF_ONLY and user.is_staff is False:
            return False

        if (
            (self.owner == user)
            or (user.is_superuser)
            or (user.has_perm("video.change_video"))
            or (user in self.additional_owners.all())
        ):
            return True
        else:
            return False

    @property
    def get_encoding_step(self):
        """Get the current encoding step of a video."""
        try:
            es = EncodingStep.objects.get(video=self)
        except ObjectDoesNotExist:
            return ""
        return "%s : %s" % (es.num_step, es.desc_step)

    get_encoding_step.fget.short_description = _("Encoding step")

    def get_player_height(self):
        """
        Get the default player height (half size for audio files).

        This height is mostly valid when in iframe mode,
         as in main mode height is set by % of window.
        """
        return 360 if self.is_video else 244

    def get_thumbnail_url(self):
        """Get a thumbnail url for the video."""
        request = None
        if self.thumbnail and self.thumbnail.file_exist():
            thumbnail_url = "".join(
                [
                    "//",
                    get_current_site(request).domain,
                    self.thumbnail.file.url,
                ]
            )
        else:
            thumbnail_url = "".join(
                [
                    "//",
                    get_current_site(request).domain,
                    static(DEFAULT_THUMBNAIL),
                ]
            )
        return thumbnail_url

    @property
    def get_thumbnail_admin(self):
        thumbnail_url = ""
        # fix title for xml description
        title = re.sub(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]", "", self.title)
        if self.thumbnail and self.thumbnail.file_exist():
            im = get_thumbnail(self.thumbnail.file, "100x100", crop="center", quality=72)
            thumbnail_url = im.url
            # <img src="{{ im.url }}" width="{{ im.width }}"
            # height="{{ im.height }}" loading="lazy">
        else:
            thumbnail_url = static(DEFAULT_THUMBNAIL)
        return format_html(
            '<img style="max-width:100px" '
            'src="%s" alt="%s" loading="lazy"/>'
            % (
                thumbnail_url,
                title.replace("{", "").replace("}", "").replace('"', "'"),
            )
        )

    get_thumbnail_admin.fget.short_description = _("Thumbnails")

    def get_thumbnail_card(self):
        """Return thumbnail image card of current video."""
        thumbnail_url = ""
        if self.thumbnail and self.thumbnail.file_exist():
            im = get_thumbnail(self.thumbnail.file, "x170", crop="center", quality=72)
            thumbnail_url = im.url
            # <img src="{{ im.url }}" width="{{ im.width }}"
            # height="{{ im.height }}" loading="lazy">
        else:
            thumbnail_url = static(DEFAULT_THUMBNAIL)
        return (
            '<img class="pod-thumbnail" src="%s" alt="%s"\
            loading="lazy"/>'
            % (thumbnail_url, self.title)
        )

    @property
    def duration_in_time(self):
        """Get the duration of a video."""
        return time.strftime("%H:%M:%S", time.gmtime(self.duration))

    duration_in_time.fget.short_description = _("Duration")

    @property
    def encoded(self):
        """Get the encoded status of a video."""
        return (
            self.get_playlist_master() is not None
            or self.get_video_mp4() is not None
            or self.get_video_m4a() is not None
        )

    encoded.fget.short_description = _("Is the video encoded?")

    @property
    def get_version(self):
        """Get the version of a video."""
        try:
            return self.videoversion.version
        except VideoVersion.DoesNotExist:
            return "O"

    def get_other_version(self):
        """Get other versions of a video."""
        version = []
        for app in THIRD_PARTY_APPS:
            mod = importlib.import_module("pod.%s.models" % app)
            if hasattr(mod, capfirst(app)):
                video_app = eval(
                    "mod.%s.objects.filter(video__id=%s).all()" % (capfirst(app), self.id)
                )
                if (
                    app == "interactive"
                    and video_app.first() is not None
                    and video_app.first().is_interactive() is False
                ):
                    video_app = False
                if video_app:
                    url = reverse(
                        "%(app)s:video_%(app)s" % {"app": app},
                        kwargs={"slug": self.slug},
                    )
                    version.append(
                        {
                            "app": app,
                            "url": url,
                            "link": VERSION_CHOICES_DICT[app.capitalize()[0]],
                        }
                    )
        return version

    def get_default_version_link(self, slug_private):
        """Get link of the version of a video."""
        for version in self.get_other_version():
            if version["link"] == VERSION_CHOICES_DICT[self.get_version]:
                if slug_private:
                    return version["url"] + slug_private + "/"
                else:
                    return version["url"]

    def get_viewcount(self, from_nb_day=0):
        """Get the view counter of a video."""
        if from_nb_day > 0:
            d = datetime.date.today() - timezone.timedelta(days=from_nb_day)
            set = self.viewcount_set.filter(date__gte=d)
        else:
            set = self.viewcount_set.all()

        count_sum = set.aggregate(Sum("count"))

        if count_sum["count__sum"] is None:
            return 0
        return count_sum["count__sum"]

    def get_absolute_url(self):
        """Get the video absolute URL."""
        return reverse("video:video", args=[str(self.slug)])

    def get_full_url(self, request=None):
        """Get the video full URL."""
        full_url = "".join(
            ["//", get_current_site(request).domain, self.get_absolute_url()]
        )
        return full_url

    def get_hashkey(self):
        return hashlib.sha256(
            ("%s-%s" % (SECRET_KEY, self.id)).encode("utf-8")
        ).hexdigest()

    def delete(self):
        """Delete the current video file and db object."""
        if self.video:
            if os.path.isfile(self.video.path):
                os.remove(self.video.path)
        if self.overview:
            if os.path.isfile(self.overview.path):
                os.remove(self.overview.path)
        super(Video, self).delete()

    def get_playlist_master(self):
        try:
            return PlaylistVideo.objects.get(
                name="playlist",
                video=self,
                encoding_format="application/x-mpegURL",
            )
        except PlaylistVideo.DoesNotExist:
            return None

    def get_video_m4a(self):
        """Get the audio (m4a) version of the video."""
        try:
            return EncodingAudio.objects.get(
                name="audio", video=self, encoding_format="video/mp4"
            )
        except EncodingAudio.DoesNotExist:
            return None

    def get_video_mp3(self):
        """Get the audio (mp3) version of the video."""
        try:
            return EncodingAudio.objects.get(
                name="audio", video=self, encoding_format="audio/mp3"
            )
        except EncodingAudio.DoesNotExist:
            return None

    def get_video_mp4(self):
        """Get the mp4 version of the video."""
        return EncodingVideo.objects.filter(video=self, encoding_format="video/mp4")

    def get_video_json(self, extensions):
        extension_list = extensions.split(",") if extensions else []
        list_video = EncodingVideo.objects.filter(video=self)
        dict_src = Video.get_media_json(extension_list, list_video)
        sorted_dict_src = {
            x: sorted(dict_src[x], key=lambda i: i["height"]) for x in dict_src.keys()
        }
        return sorted_dict_src

    def get_video_mp4_json(self):
        list_mp4 = self.get_video_json(extensions="mp4")
        return list_mp4["mp4"] if list_mp4.get("mp4") else []

    def get_audio_json(self, extensions):
        extension_list = extensions.split(",") if extensions else []
        list_audio = EncodingAudio.objects.filter(name="audio", video=self)
        dict_src = Video.get_media_json(extension_list, list_audio)
        return dict_src

    def get_audio_and_video_json(self, extensions):
        return {
            **self.get_video_json(extensions),
            **self.get_audio_json(extensions),
        }

    @staticmethod
    def get_media_json(extension_list, list_video):
        dict_src = {}
        for media in list_video:
            file_extension = splitext(media.source_file.url)[-1]
            if not extension_list or file_extension[1:] in extension_list:
                media_height = None
                if hasattr(media, "height"):
                    media_height = media.height
                video_object = {
                    "id": media.id,
                    "type": media.encoding_format,
                    "src": media.source_file.url,
                    "height": media_height,
                    "extension": file_extension,
                    "label": media.name,
                }
                dict_entry = dict_src.get(file_extension[1:], None)
                if dict_entry is None:
                    dict_src[file_extension[1:]] = [video_object]
                else:
                    dict_entry.append(video_object)
        return dict_src

    def get_json_to_index(self):
        try:
            current_site = Site.objects.get_current()
            data_to_dump = {
                "id": self.id,
                "title": "%s" % self.title,
                "owner": "%s" % self.owner.username,
                "owner_full_name": "%s" % self.owner.get_full_name(),
                "date_added": "%s" % self.date_added.strftime("%Y-%m-%dT%H:%M:%S")
                if self.date_added
                else None,
                "date_evt": "%s" % self.date_evt.strftime("%Y-%m-%dT%H:%M:%S")
                if self.date_evt
                else None,
                "description": "%s" % self.description,
                "thumbnail": "%s" % self.get_thumbnail_url(),
                "duration": "%s" % self.duration,
                "tags": list(
                    [
                        {"name": name[0], "slug": slugify(name)}
                        for name in Tag.objects.get_for_object(self).values_list("name")
                    ]
                ),
                "type": {"title": self.type.title, "slug": self.type.slug},
                "disciplines": list(
                    self.discipline.all()
                    .filter(site=current_site)
                    .values("title", "slug")
                ),
                "channels": list(
                    self.channel.all().filter(site=current_site).values("title", "slug")
                ),
                "themes": list(self.theme.all().values("title", "slug")),
                "contributors": list(self.contributor_set.values("name", "role")),
                "chapters": list(self.chapter_set.values("title", "slug")),
                "overlays": list(self.overlay_set.values("title", "slug")),
                "full_url": self.get_full_url(),
                "is_restricted": self.is_restricted,
                "password": True if self.password != "" else False,
                "duration_in_time": self.duration_in_time,
                "mediatype": "video" if self.is_video else "audio",
                "cursus": "%s" % CURSUS_CODES_DICT[self.cursus],
                "main_lang": "%s" % LANG_CHOICES_DICT[self.main_lang],
            }
            return json.dumps(data_to_dump)
        except ObjectDoesNotExist as e:
            logger.error(
                "An error occured during get_json_to_index"
                " for video %s: %s" % (self.id, e)
            )
            return json.dumps({})

    def get_json_to_video_view(video, other_data_to_dump):
        try:
            video_src = {}
            if video.is_video:
                video_src["mp4"] = video.get_video_mp4_json()
                m3u8 = video.get_playlist_master()
                if m3u8:
                    video_src["m3u8"] = {
                        "src": m3u8.source_file.url,
                        "type": m3u8.encoding_format,
                    }
            else:
                m4a = video.get_video_m4a()
                video_src["m4a"] = {
                    "src": m4a.source_file.url,
                    "type": m4a.encoding_format,
                }

            list_track = list(
                map(
                    lambda t: {
                        "id": t.id,
                        "kind": t.kind,
                        "src": t.src.file.url,
                        "srclang": t.lang,
                        "label": t.get_label_lang(),
                    },
                    video.track_set.all(),
                ),
            )
            list_overlay = list(
                map(
                    lambda o: {
                        "start": o.time_start,
                        "end": o.time_end,
                        "content": o.content,
                        "align": o.position,
                        "showBackground": o.background,
                    },
                    video.overlay_set.all(),
                ),
            )
            list_chapter = list(
                map(
                    lambda c: {"time_start": c.time_start, "id": c.id, "title": c.title},
                    video.chapter_set.all(),
                ),
            )
            overview = video.overview.url if (video.overview) else ""
            data_to_dump = {
                "status": "ok",
                "version": video.get_version,
                "slug": video.slug,
                "title": video.title,
                "tracks": list_track,
                "is_video": video.is_video,
                "src": video_src,
                "is_360": video.is_360,
                "thumbnail": video.get_thumbnail_url(),
                "overview": overview,
                "overlay": list_overlay,
                "chapter": list_chapter,
            }
            if hasattr(video, "enrichmentvtt"):
                data_to_dump["enrichtracksrc"] = video.enrichmentvtt.src.file.url
            for k in other_data_to_dump:
                data_to_dump[k] = other_data_to_dump[k]
            return json.dumps(data_to_dump)
        except ObjectDoesNotExist as e:
            logger.error(
                "An error occured during get_json_to_video_view"
                " for video %s: %s" % (video.id, e)
            )
            return json.dumps({})

    def get_main_lang(self):
        return "%s" % LANG_CHOICES_DICT[self.main_lang]

    def get_cursus(self):
        return "%s" % CURSUS_CODES_DICT[self.cursus]

    def get_licence(self):
        return "%s" % LICENCE_CHOICES_DICT[self.licence]

    def get_dublin_core(self):
        contributors = []
        current_site = Site.objects.get_current()
        for contrib in self.contributor_set.values_list("name", "role"):
            contributors.append(" ".join(contrib))
        try:
            data_to_dump = {
                "dc.title": "%s" % self.title,
                "dc.creator": "%s" % self.owner.get_full_name(),
                "dc.description": "%s" % self.description,
                "dc.subject": "%s, %s"
                % (
                    self.type.title,
                    ", ".join(
                        self.discipline.all()
                        .filter(sites=current_site)
                        .values_list("title", flat=True)
                    ),
                ),
                "dc.publisher": TITLE_ETB,
                "dc.contributor": ", ".join(contributors),
                "dc.date": "%s" % self.date_added.strftime("%Y/%m/%d"),
                "dc.type": "video" if self.is_video else "audio",
                "dc.identifier": "http:%s" % self.get_full_url(),
                "dc.language": "%s" % self.main_lang,
                "dc.coverage": DEFAULT_DC_COVERAGE,
                "dc.rights": self.licence if (self.licence) else DEFAULT_DC_RIGHTS,
                "dc.format": "video/mp4" if self.is_video else "audio/mp3",
            }
            return data_to_dump
        except ObjectDoesNotExist as e:
            logger.error(
                "An error occured during get_dublin_core"
                " for video %s: %s" % (self.id, e)
            )
            return {}


class UpdateOwner(models.Model):
    class Meta:
        verbose_name = _("Update Owner")
        verbose_name_plural = _("Update Owners")


def remove_video_file(video):
    if video.video:
        log_file = os.path.join(
            os.path.dirname(video.video.path), "%04d" % video.id, "info_video.json"
        )
        if os.path.isfile(log_file):
            os.remove(log_file)
    if video.overview:
        image_overview = os.path.join(
            os.path.dirname(video.overview.path), "overview.png"
        )
        if os.path.isfile(image_overview):
            os.remove(image_overview)
        video.overview.delete()


@receiver(post_save, sender=Video)
def default_site(sender, instance, created, **kwargs):
    if len(instance.sites.all()) == 0:
        instance.sites.add(Site.objects.get_current())


@receiver(pre_delete, sender=Video, dispatch_uid="pre_delete-video_files_removal")
def video_files_removal(sender, instance, using, **kwargs):
    remove_video_file(instance)

    previous_encoding_video = EncodingVideo.objects.filter(video=instance)
    if len(previous_encoding_video) > 0:
        for encoding in previous_encoding_video:
            encoding.delete()

    previous_encoding_audio = EncodingAudio.objects.filter(video=instance)
    if len(previous_encoding_audio) > 0:
        for encoding in previous_encoding_audio:
            encoding.delete()

    previous_encoding_playlist = PlaylistVideo.objects.filter(video=instance)
    if len(previous_encoding_playlist) > 0:
        for encoding in previous_encoding_playlist:
            encoding.delete()


class ViewCount(models.Model):
    video = models.ForeignKey(
        Video, verbose_name=_("Video"), editable=False, on_delete=models.CASCADE
    )
    date = models.DateField(_("Date"), default=date.today, editable=False)
    count = models.IntegerField(_("Number of view"), default=0, editable=False)

    @property
    def sites(self):
        return self.video.sites

    class Meta:
        unique_together = ("video", "date")
        verbose_name = _("View count")
        verbose_name_plural = _("View counts")


class VideoRendition(models.Model):
    resolution = models.CharField(
        _("resolution"),
        max_length=50,
        unique=True,
        help_text=_(
            "Please use the only format x. i.e.: "
            + "<em>640x360</em> or <em>1280x720</em>"
            + " or <em>1920x1080</em>."
        ),
    )
    minrate = models.CharField(
        _("minrate"),
        max_length=50,
        help_text=_(
            "Please use the only format k. i.e.: "
            + "<em>300k</em> or <em>600k</em>"
            + " or <em>1000k</em>."
        ),
    )
    video_bitrate = models.CharField(
        _("bitrate video"),
        max_length=50,
        help_text=_(
            "Please use the only format k. i.e.: "
            + "<em>300k</em> or <em>600k</em>"
            + " or <em>1000k</em>."
        ),
    )
    maxrate = models.CharField(
        _("maxrate"),
        max_length=50,
        help_text=_(
            "Please use the only format k. i.e.: "
            + "<em>300k</em> or <em>600k</em>"
            + " or <em>1000k</em>."
        ),
    )
    encoding_resolution_threshold = models.PositiveIntegerField(
        _("encoding resolution threshold"), default=0, validators=[MaxValueValidator(100)]
    )
    audio_bitrate = models.CharField(
        _("bitrate audio"),
        max_length=50,
        help_text=_(
            "Please use the only format k. i.e.: "
            + "<em>300k</em> or <em>600k</em>"
            + " or <em>1000k</em>."
        ),
    )
    encode_mp4 = models.BooleanField(_("Make a MP4 version"), default=False)
    sites = models.ManyToManyField(Site)

    @property
    def height(self):
        return int(self.resolution.split("x")[1])

    @property
    def width(self):
        return int(self.resolution.split("x")[0])

    class Meta:
        # ordering = ['height'] # Not work
        verbose_name = _("rendition")
        verbose_name_plural = _("renditions")

    def __str__(self):
        return "VideoRendition num %s with resolution %s" % (
            "%04d" % self.id,
            self.resolution,
        )

    def clean_bitrate(self):
        if self.video_bitrate and "k" not in self.video_bitrate:
            msg = "Error in %s: " % _("bitrate video")
            raise ValidationError(
                "%s %s"
                % (
                    msg,
                    VideoRendition._meta.get_field("video_bitrate").help_text,
                )
            )
        else:
            vb = self.video_bitrate.replace("k", "")
            if not vb.isdigit():
                msg = "Error in %s: " % _("bitrate video")
                raise ValidationError(
                    "%s %s"
                    % (
                        msg,
                        VideoRendition._meta.get_field("video_bitrate").help_text,
                    )
                )
        if self.maxrate and "k" not in self.maxrate:
            msg = "Error in %s: " % _("maxrate")
            raise ValidationError(
                "%s %s" % (msg, VideoRendition._meta.get_field("maxrate").help_text)
            )
        else:
            vb = self.video_bitrate.replace("k", "")
            if not vb.isdigit():
                msg = "Error in %s: " % _("maxrate")
                raise ValidationError(
                    "%s %s" % (msg, VideoRendition._meta.get_field("maxrate").help_text)
                )
        if self.minrate and "k" not in self.minrate:
            msg = "Error in %s: " % _("minrate")
            raise ValidationError(
                "%s %s" % (msg, VideoRendition._meta.get_field("minrate").help_text)
            )
        else:
            vb = self.video_bitrate.replace("k", "")
            if not vb.isdigit():
                msg = "Error in %s: " % _("minrate")
                raise ValidationError(
                    "%s %s" % (msg, VideoRendition._meta.get_field("minrate").help_text)
                )

    def clean(self):
        if self.resolution and "x" not in self.resolution:
            raise ValidationError(VideoRendition._meta.get_field("resolution").help_text)
        else:
            res = self.resolution.replace("x", "")
            if not res.isdigit():
                raise ValidationError(
                    VideoRendition._meta.get_field("resolution").help_text
                )

        self.clean_bitrate()

        if self.audio_bitrate and "k" not in self.audio_bitrate:
            msg = "Error in %s: " % _("bitrate audio")
            raise ValidationError(
                "%s %s"
                % (
                    msg,
                    VideoRendition._meta.get_field("audio_bitrate").help_text,
                )
            )
        else:
            vb = self.audio_bitrate.replace("k", "")
            if not vb.isdigit():
                msg = "Error in %s: " % _("bitrate audio")
                raise ValidationError(
                    "%s %s"
                    % (
                        msg,
                        VideoRendition._meta.get_field("audio_bitrate").help_text,
                    )
                )


@receiver(post_save, sender=VideoRendition)
def default_site_videorendition(sender, instance, created, **kwargs):
    if len(instance.sites.all()) == 0:
        instance.sites.add(Site.objects.get_current())


class EncodingVideo(models.Model):
    name = models.CharField(
        _("Name"),
        max_length=10,
        choices=ENCODING_CHOICES,
        default="360p",
        help_text=_("Please use the only format in encoding choices:")
        + " %s" % " ".join(str(key) for key, value in ENCODING_CHOICES),
    )
    video = models.ForeignKey(Video, verbose_name=_("Video"), on_delete=models.CASCADE)
    rendition = models.ForeignKey(
        VideoRendition, verbose_name=_("rendition"), on_delete=models.CASCADE
    )
    encoding_format = models.CharField(
        _("Format"),
        max_length=22,
        choices=FORMAT_CHOICES,
        default="video/mp4",
        help_text=_("Please use the only format in format choices:")
        + " %s" % " ".join(str(key) for key, value in FORMAT_CHOICES),
    )
    source_file = models.FileField(
        _("encoding source file"),
        upload_to=get_storage_path_video,
        max_length=255,
    )

    @property
    def sites(self):
        return self.video.sites

    @property
    def sites_all(self):
        return self.video.sites_set.all()

    def clean(self):
        if self.name:
            if self.name not in dict(ENCODING_CHOICES):
                raise ValidationError(EncodingVideo._meta.get_field("name").help_text)
        if self.encoding_format:
            if self.encoding_format not in dict(FORMAT_CHOICES):
                raise ValidationError(
                    EncodingVideo._meta.get_field("encoding_format").help_text
                )

    class Meta:
        ordering = ["name"]
        verbose_name = _("Encoding video")
        verbose_name_plural = _("Encoding videos")

    def __str__(self):
        return "EncodingVideo num: %s with resolution %s for video %s in %s" % (
            "%04d" % self.id,
            self.name,
            self.video.id,
            self.encoding_format,
        )

    @property
    def owner(self):
        return self.video.owner

    @property
    def height(self):
        return int(self.rendition.resolution.split("x")[1])

    @property
    def width(self):
        return int(self.rendition.resolution.split("x")[0])

    def delete(self):
        if self.source_file:
            if os.path.isfile(self.source_file.path):
                os.remove(self.source_file.path)
        super(EncodingVideo, self).delete()


class EncodingAudio(models.Model):
    name = models.CharField(
        _("Name"),
        max_length=10,
        choices=ENCODING_CHOICES,
        default="audio",
        help_text=_("Please use the only format in encoding choices:")
        + " %s" % " ".join(str(key) for key, value in ENCODING_CHOICES),
    )
    video = models.ForeignKey(Video, verbose_name=_("Video"), on_delete=models.CASCADE)
    encoding_format = models.CharField(
        _("Format"),
        max_length=22,
        choices=FORMAT_CHOICES,
        default="audio/mp3",
        help_text=_("Please use the only format in format choices:")
        + " %s" % " ".join(str(key) for key, value in FORMAT_CHOICES),
    )
    source_file = models.FileField(
        _("encoding source file"),
        upload_to=get_storage_path_video,
        max_length=255,
    )

    @property
    def sites(self):
        return self.video.sites

    @property
    def sites_all(self):
        return self.video.sites_set.all()

    class Meta:
        ordering = ["name"]
        verbose_name = _("Encoding audio")
        verbose_name_plural = _("Encoding audios")

    def clean(self):
        if self.name:
            if self.name not in dict(ENCODING_CHOICES):
                raise ValidationError(EncodingAudio._meta.get_field("name").help_text)
        if self.encoding_format:
            if self.encoding_format not in dict(FORMAT_CHOICES):
                raise ValidationError(
                    EncodingAudio._meta.get_field("encoding_format").help_text
                )

    def __str__(self):
        return "EncodingAudio num: %s for video %s in %s" % (
            "%04d" % self.id,
            self.video.id,
            self.encoding_format,
        )

    @property
    def owner(self):
        return self.video.owner

    def delete(self):
        if self.source_file:
            if os.path.isfile(self.source_file.path):
                os.remove(self.source_file.path)
        super(EncodingAudio, self).delete()


class PlaylistVideo(models.Model):
    name = models.CharField(
        _("Name"),
        max_length=10,
        choices=ENCODING_CHOICES,
        default="360p",
        help_text=_("Please use the only format in encoding choices:")
        + " %s" % " ".join(str(key) for key, value in ENCODING_CHOICES),
    )
    video = models.ForeignKey(Video, verbose_name=_("Video"), on_delete=models.CASCADE)
    encoding_format = models.CharField(
        _("Format"),
        max_length=22,
        choices=FORMAT_CHOICES,
        default="application/x-mpegURL",
        help_text=_("Please use the only format in format choices:")
        + " %s" % " ".join(str(key) for key, value in FORMAT_CHOICES),
    )
    source_file = models.FileField(
        _("encoding source file"),
        upload_to=get_storage_path_video,
        max_length=255,
    )

    class Meta:
        verbose_name = _("Video Playlist")
        verbose_name_plural = _("Video Playlists")

    @property
    def sites(self):
        return self.video.sites

    @property
    def sites_all(self):
        return self.video.sites_set.all()

    def clean(self):
        if self.name:
            if self.name not in dict(ENCODING_CHOICES):
                raise ValidationError(PlaylistVideo._meta.get_field("name").help_text)
        if self.encoding_format:
            if self.encoding_format not in dict(FORMAT_CHOICES):
                raise ValidationError(
                    PlaylistVideo._meta.get_field("encoding_format").help_text
                )

    def __str__(self):
        return "Playlist num: %s for video %s in %s" % (
            "%04d" % self.id,
            self.video.id,
            self.encoding_format,
        )

    @property
    def owner(self):
        return self.video.owner

    def delete(self):
        if self.source_file:
            if os.path.isfile(self.source_file.path):
                os.remove(self.source_file.path)
        super(PlaylistVideo, self).delete()


class EncodingLog(models.Model):
    video = models.OneToOneField(
        Video, verbose_name=_("Video"), editable=False, on_delete=models.CASCADE
    )
    log = models.TextField(null=True, blank=True, editable=False)
    logfile = models.FileField(max_length=255, blank=True, null=True)

    @property
    def sites(self):
        return self.video.sites

    @property
    def sites_all(self):
        return self.video.sites_set.all()

    class Meta:
        ordering = ["video"]
        verbose_name = _("Encoding log")
        verbose_name_plural = _("Encoding logs")

    def __str__(self):
        return "Log for encoding video %s" % (self.video.id)


class VideoVersion(models.Model):
    video = models.OneToOneField(
        Video, verbose_name=_("Video"), editable=False, on_delete=models.CASCADE
    )
    version = models.CharField(
        _("Video version"),
        max_length=1,
        blank=True,
        choices=VERSION_CHOICES,
        default="O",
        help_text=_("Video default version."),
    )

    class Meta:
        verbose_name = _("Video version")
        verbose_name_plural = _("Video versions")

    @property
    def sites(self):
        return self.video.sites

    @property
    def sites_all(self):
        return self.video.sites_set.all()

    def __str__(self):
        return "Choice for default video version: %s - %s" % (
            self.video.id,
            self.version,
        )


class EncodingStep(models.Model):
    video = models.OneToOneField(
        Video, verbose_name=_("Video"), editable=False, on_delete=models.CASCADE
    )
    num_step = models.IntegerField(default=0, editable=False)
    desc_step = models.CharField(null=True, max_length=255, blank=True, editable=False)

    @property
    def sites(self):
        return self.video.sites

    @property
    def sites_all(self):
        return self.video.sites_set.all()

    class Meta:
        ordering = ["video"]
        verbose_name = _("Encoding step")
        verbose_name_plural = _("Encoding steps")

    def __str__(self):
        return "Step for encoding video %s" % (self.video.id)


class Notes(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    video = models.ForeignKey(Video, on_delete=models.CASCADE)
    note = models.TextField(_("Note"), null=True, blank=True)

    @property
    def sites(self):
        return self.video.sites

    @property
    def sites_all(self):
        return self.video.sites_set.all()

    class Meta:
        verbose_name = _("Note")
        verbose_name_plural = _("Notes")
        unique_together = ("video", "user")

    def __str__(self):
        return "%s-%s" % (self.user.username, self.video)


class AdvancedNotes(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    video = models.ForeignKey(Video, on_delete=models.CASCADE)
    status = models.CharField(
        _("Availability level"),
        max_length=1,
        choices=NOTES_STATUS,
        default="0",
        help_text=_("Select an availability level for the note."),
    )
    note = models.TextField(_("Note"), null=True, blank=True)
    timestamp = models.IntegerField(_("Timestamp"), null=True, blank=True)
    added_on = models.DateTimeField(_("Date added"), default=timezone.now)
    modified_on = models.DateTimeField(_("Date modified"), default=timezone.now)

    class Meta:
        verbose_name = _("Advanced Note")
        verbose_name_plural = _("Advanced Notes")
        unique_together = ("video", "user", "timestamp", "status")

    @property
    def sites(self):
        return self.video.sites

    @property
    def sites_all(self):
        return self.video.sites_set.all()

    def __str__(self):
        return "%s-%s-%s" % (self.user.username, self.video, self.timestamp)

    def clean(self):
        if not self.note:
            raise ValidationError(AdvancedNotes._meta.get_field("note").help_text)
        if not self.status or self.status not in dict(NOTES_STATUS):
            raise ValidationError(AdvancedNotes._meta.get_field("status").help_text)
        if (
            self.timestamp is None
            or self.timestamp < 0
            or (self.video.duration and self.timestamp > self.video.duration)
        ):
            raise ValidationError(AdvancedNotes._meta.get_field("timestamp").help_text)

    def timestampstr(self):
        if self.timestamp is None:
            return "--:--:--"
        seconds = int(self.timestamp)
        hours = int(seconds / 3600)
        seconds -= hours * 3600
        minutes = int(seconds / 60)
        seconds -= minutes * 60
        hours = "0" + str(hours) if hours < 10 else str(hours)
        minutes = "0" + str(minutes) if minutes < 10 else str(minutes)
        seconds = "0" + str(seconds) if seconds < 10 else str(seconds)
        return hours + ":" + minutes + ":" + seconds


class NoteComments(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    parentNote = models.ForeignKey(AdvancedNotes, on_delete=models.CASCADE)
    parentCom = models.ForeignKey(
        "NoteComments", blank=True, null=True, on_delete=models.CASCADE
    )
    status = models.CharField(
        _("Availability level"),
        max_length=1,
        choices=NOTES_STATUS,
        default="0",
        help_text=_("Select an availability level for the comment."),
    )
    comment = models.TextField(_("Comment"), null=True, blank=True)
    added_on = models.DateTimeField(_("Date added"), default=timezone.now)
    modified_on = models.DateTimeField(_("Date modified"), default=timezone.now)

    class Meta:
        verbose_name = _("Note comment")
        verbose_name_plural = _("Note comments")

    def __str__(self):
        return "%s-%s-%s" % (self.user.username, self.parentNote, self.comment)

    def clean(self):
        if not self.comment:
            raise ValidationError(NoteComments._meta.get_field("comment").help_text)
        if not self.status or self.status not in dict(NOTES_STATUS):
            raise ValidationError(NoteComments._meta.get_field("status").help_text)


class VideoToDelete(models.Model):
    date_deletion = models.DateField(
        _("Date for deletion"), default=date.today, unique=True
    )
    video = models.ManyToManyField(Video, verbose_name=_("Videos"))

    class Meta:
        verbose_name = _("Video to delete")
        verbose_name_plural = _("Videos to delete")

    def __str__(self):
        return "%s - nb videos : %s" % (self.date_deletion, self.video.count())


class Comment(models.Model):
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    parent = models.ForeignKey(
        "self",
        related_name="children",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    direct_parent = models.ForeignKey(
        "self",
        related_name="direct_children",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    video = models.ForeignKey(Video, on_delete=models.CASCADE)
    added = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Comment")
        verbose_name_plural = _("Comments")

    @property
    def number_vote(self):
        self.vote_set.all().count()

    @property
    def get_children(self):
        return Comment.objects.filter(parent_id=self.id).order_by("id")

    def get_json_children(self, user_id):
        return list(
            self.get_children.annotate(nbr_vote=Count("vote", distinct=True))
            .annotate(
                author_name=Concat("author__first_name", Value(" "), "author__last_name")
            )
            .annotate(
                is_owner=Case(
                    When(author__id=user_id, then=Value(True)),
                    default=Value(False),
                    output_field=BooleanField(),
                )
            )
            .values(
                "id",
                "parent__id",
                "direct_parent__id",
                "is_owner",
                "author_name",
                "added",
                "content",
                "nbr_vote",
            )
        )

    def __str__(self):
        return self.content


class Vote(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE)

    class Meta:
        verbose_name = _("Vote")
        verbose_name_plural = _("Votes")

    def __str__(self):
        return str(self.user)


class Category(models.Model):
    title = models.CharField(
        _("Category title"),
        max_length=100,
        help_text=_(
            "Please choose a title as short and accurate as "
            "possible, reflecting the main subject / context "
            "of the content. (max length: 100 characters)"
        ),
    )
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    video = models.ManyToManyField(
        Video,
        verbose_name=_("Videos"),
        blank=True,
        help_text=_(
            'Hold down "Control", or "Command" ' "on a Mac, to select more than one."
        ),
    )
    slug = models.SlugField(
        _("Slug"),
        unique=True,
        max_length=110,
        help_text=_(
            'Used to access this instance, the "slug" is a short label '
            + "containing only letters, numbers, underscore or dash top."
        ),
        editable=False,
    )

    def save(self, *args, **kwargs):
        self.slug = "%s-%s" % (self.owner.id, slugify(self.title))
        super(Category, self).save(*args, **kwargs)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ["title", "id"]
        verbose_name = _("Category")
        verbose_name_plural = _("Categories")
