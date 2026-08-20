import uuid

from django.db import models


class Generation(models.Model):
    """One run of the wizard: the brief, the chosen template, and its outcome.

    The client POSTs a brief, gets an id back, then polls this row until the
    status leaves ``pending``/``running`` -- generating two slides takes far
    longer than a request should be held open.
    """

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        RUNNING = 'running', 'Running'
        DONE = 'done', 'Done'
        FAILED = 'failed', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template_id = models.CharField(max_length=64)
    answers = models.JSONField()
    # optional client-supplied brand logo, composited onto every slide
    logo = models.ImageField(upload_to='logos/', null=True, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    error = models.TextField(blank=True, default='')
    demo_mode = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.id} ({self.template_id}, {self.status})'

    @property
    def is_finished(self):
        return self.status in (self.Status.DONE, self.Status.FAILED)


class GeneratedImage(models.Model):
    """One rendered slide.

    ``filled_layout`` and ``prompt_used`` are kept deliberately: when a slide
    comes out wrong they are the only way to tell whether the layout, the copy
    stage, or the image prompt was at fault.
    """

    generation = models.ForeignKey(
        Generation, related_name='images', on_delete=models.CASCADE
    )
    page = models.PositiveIntegerField()
    image = models.ImageField(upload_to='generated/')
    filled_layout = models.JSONField(null=True, blank=True)
    prompt_used = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['page']
        unique_together = [('generation', 'page')]

    def __str__(self):
        return f'{self.generation_id} page {self.page}'
