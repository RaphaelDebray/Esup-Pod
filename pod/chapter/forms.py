from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext as _

from pod.chapter.models import Chapter
from pod.chapter.utils import vtt_to_chapter
from pod.main.forms_utils import add_placeholder_and_asterisk

if getattr(settings, "USE_PODFILE", False):
    FILEPICKER = True
    from pod.podfile.models import CustomFileModel
    from pod.podfile.widgets import CustomFileWidget
else:
    FILEPICKER = False
    from pod.main.models import CustomFileModel


class ChapterForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(ChapterForm, self).__init__(*args, **kwargs)
        self.fields["video"].widget = forms.HiddenInput()
        self.fields["time_start"].widget.attrs["min"] = 0
        try:
            self.fields["time_start"].widget.attrs["max"] = (
                self.instance.video.duration - 1
            )
        except Exception:
            self.fields["time_start"].widget.attrs["max"] = 36000
        self.fields = add_placeholder_and_asterisk(self.fields)

    class Meta:
        model = Chapter
        fields = "__all__"


class ChapterImportForm(forms.Form):
    file = forms.ModelChoiceField(queryset=CustomFileModel.objects.all())

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        self.video = kwargs.pop("video")
        super(ChapterImportForm, self).__init__(*args, **kwargs)
        if FILEPICKER:
            self.fields["file"].widget = CustomFileWidget(type="file")
            self.fields["file"].queryset = CustomFileModel.objects.filter(
                created_by=self.user
            )
        else:
            self.fields["file"].queryset = CustomFileModel.objects.all()
        self.fields["file"].label = _("File to import")

    def clean_file(self):
        msg = vtt_to_chapter(self.cleaned_data["file"], self.video)
        if msg:
            raise ValidationError("Error ! {0}".format(msg))
        return self.cleaned_data["file"]
