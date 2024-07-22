from django.db import models

# models.py 

from django.db import models

class Automation(models.Model):
    name = models.CharField(max_length=400)
    ac_url = models.URLField(max_length=200, unique=True)
    ac_json = models.JSONField()

    def __str__(self):
        return self.name
    

class Contact(models.Model):
    first_name = models.CharField(max_length=200)
    last_name = models.CharField(max_length=200)
    email = models.CharField(max_length=200)
    ac_id = models.CharField(max_length=200, unique=True)
    hl_id = models.CharField(max_length=200, unique=True, blank=True, null=True)
    ac_json = models.JSONField(blank=True, null=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"
    

class CustomField(models.Model):
    ac_id = models.CharField(max_length=200, unique=True)
    hl_id = models.CharField(max_length=200, unique=True, blank=True, null=True)
    type = models.CharField(max_length=200)
    ac_title = models.CharField(max_length=200)
    ac_json = models.JSONField(blank=True, null=True)

    def __str__(self):
        if self.ac_json and 'type' in self.ac_json:
            return f"{self.ac_title} ({self.ac_json['type']})"
        else:
            return self.ac_title
        

class ContactCustomField(models.Model):
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="custom_field_values")
    custom_field = models.ForeignKey(CustomField, on_delete=models.CASCADE)
    value = models.CharField(max_length=500)

    def __str__(self):
        return f"{self.contact} - {self.custom_field}: {self.value}"
    


class HLPipeline(models.Model):
    hl_id = models.CharField(max_length=200, unique=True)
    hl_json = models.JSONField()
    name = models.CharField(max_length=200)

    def __str__(self):
        return self.name


class PipeLine(models.Model):
    ac_id = models.CharField(max_length=200, unique=True)
    ac_json = models.JSONField()
    name = models.CharField(max_length=200)
    hl_pipeline = models.ForeignKey(
        HLPipeline, on_delete=models.CASCADE, blank=True, null=True)

    def __str__(self):
        return self.name
    

class HLDealstage(models.Model):
    hl_id = models.CharField(max_length=200, unique=True)
    hl_json = models.JSONField()
    name = models.CharField(max_length=200)
    hl_pipeline = models.ForeignKey(HLPipeline, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.hl_pipeline.name} - {self.name}"


class DealStage(models.Model):
    ac_id = models.CharField(max_length=200, unique=True)
    ac_json = models.JSONField(blank=True, null=True)  # Changed this line
    name = models.CharField(max_length=200)
    order = models.IntegerField(default=0)
    pipeline = models.ForeignKey(
        PipeLine, on_delete=models.CASCADE, blank=True, null=True)
    hl_dealstage = models.OneToOneField(
        HLDealstage, on_delete=models.CASCADE, blank=True, null=True
    )

    def __str__(self):
        return f"{self.pipeline.name if self.pipeline else 'No Pipeline'} - {self.name}"


class Deal(models.Model):
    ac_id = models.CharField(max_length=200, unique=True)
    hl_id = models.CharField(max_length=200, unique=True, blank=True, null=True)
    ac_json = models.JSONField()
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name='deals')
    stage = models.ForeignKey(DealStage, on_delete=models.CASCADE)
    title = models.CharField(max_length=200, blank=True, null=True)
    value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default='USD')
    created_date = models.DateTimeField(null=True, blank=True)
    updated_date = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.title or 'Untitled Deal'} - {self.contact}"
