"""
ResumeXpert – Custom Template Filters
"""
from django import template

register = template.Library()

@register.filter
def letter(value):
    """Convert 0→A, 1→B, 2→C, 3→D for option display."""
    try:
        return chr(65 + int(value))
    except (ValueError, TypeError):
        return str(value)

@register.filter
def subtract(value, arg):
    try:
        return int(value) - int(arg)
    except (ValueError, TypeError):
        return value

@register.filter  
def get_item(lst, i):
    try:
        return lst[int(i)]
    except (IndexError, TypeError, ValueError):
        return ''
