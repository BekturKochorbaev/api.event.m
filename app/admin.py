from django.contrib import admin

from .models import GeneratedImage, Generation


class GeneratedImageInline(admin.TabularInline):
    model = GeneratedImage
    extra = 0
    readonly_fields = ['page', 'image', 'prompt_used', 'filled_layout', 'created_at']
    can_delete = False


@admin.register(Generation)
class GenerationAdmin(admin.ModelAdmin):
    list_display = ['id', 'template_id', 'status', 'demo_mode', 'created_at']
    list_filter = ['status', 'template_id', 'demo_mode']
    readonly_fields = ['id', 'answers', 'created_at', 'updated_at']
    inlines = [GeneratedImageInline]
