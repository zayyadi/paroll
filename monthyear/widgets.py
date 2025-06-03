from datetime import date
from django.forms import widgets
from django.utils.dates import MONTHS
from django.templatetags.static import static

from monthyear.util import string_type


class MonthSelectorWidget(widgets.MultiWidget):
    def __init__(self, attrs=None):
        attrs = attrs or {} # Ensure attrs is a dict

        # Base style for sub-widgets, suitable for inline display
        sub_widget_base_class = "px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"

        # Month widget (Select)
        month_widget_attrs = attrs.copy()
        month_widget_attrs['class'] = (month_widget_attrs.get('class', '') + f' {sub_widget_base_class} flex-grow min-w-0 w-monthyear-month').strip()
        # Added w-monthyear-month for any specific JS/CSS targeting if still used

        # Year widget (NumberInput)
        year_widget_attrs = attrs.copy()
        year_widget_attrs['class'] = (year_widget_attrs.get('class', '') + f' {sub_widget_base_class} w-24 min-w-0 w-monthyear-year').strip()
        # Added w-monthyear-year

        _widgets = [
            widgets.Select(attrs=month_widget_attrs, choices=MONTHS.items()),
            widgets.NumberInput(attrs=year_widget_attrs)
        ]
        # The main attrs are passed to the MultiWidget wrapper, which might have its own class if 'widget_tweaks' adds one.
        # Or if it's rendered without widget_tweaks, it's just a wrapper div usually.
        super().__init__(_widgets, attrs)

    @property
    def media(self):
        media = self._get_media()
        media.add_css({
            'screen': (static('monthyear/field/widget_month.css'),)
        })
        return media

    def decompress(self, value):
        if value:
            if isinstance(value, string_type):
                m = int(value[5:7])
                y = int(value[:4])
                return [m, y]
            return [value.month, value.year]
        return [None, None]

    def format_output(self, rendered_widgets):
        return ''.join(rendered_widgets)

    def value_from_datadict(self, data, files, name):
        datelist = [
            widget.value_from_datadict(data, files, name + '_%s' % i)
            for i, widget in enumerate(self.widgets)]
        if not datelist[0] or not datelist[1]:
            return None
        try:
            D = date(day=1, month=int(datelist[0]),
                     year=int(datelist[1]))
        except ValueError:
            return ''
        else:
            return str(D)