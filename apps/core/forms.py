from django import forms


class StyledFormMixin:
    def apply_styles(self) -> None:
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, (forms.CheckboxInput, forms.RadioSelect)):
                css_class = "form-check-input"
            elif isinstance(widget, forms.Select):
                css_class = "form-select"
            else:
                css_class = "form-control"
            widget.attrs["class"] = f"{widget.attrs.get('class', '')} {css_class}".strip()
            if field.required:
                widget.attrs["aria-required"] = "true"
            bound_field = self[name]
            described_by = []
            if field.help_text and bound_field.id_for_label:
                described_by.append(f"{bound_field.id_for_label}-help")
            if described_by:
                widget.attrs["aria-describedby"] = " ".join(described_by)


class StyledModelForm(StyledFormMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_styles()


class StyledForm(StyledFormMixin, forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_styles()
