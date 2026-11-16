from django import template

from ledger.money import format_kopiykas, format_rate

register = template.Library()


@register.filter
def money(value):
    return format_kopiykas(value)


@register.filter
def rate(value):
    return format_rate(value)
