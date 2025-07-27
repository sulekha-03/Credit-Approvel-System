# backend/core/models.py
from django.db import models
from django.contrib.auth.models import User # For linking customers to Django's User model for authentication
from decimal import Decimal
from datetime import date

class Customer(models.Model):
    customer_id = models.AutoField(primary_key=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    age = models.IntegerField()
    phone_number = models.CharField(max_length=15, unique=True)
    monthly_salary = models.DecimalField(max_digits=10, decimal_places=2)
    approved_limit = models.DecimalField(max_digits=10, decimal_places=2)
    current_debt = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # Link to Django's User model for authentication. Null=True, Blank=True for initial data ingestion.
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.customer_id})"

    @property
    def loans_taken(self):
        # Returns all loans associated with this customer
        return self.loan_set.all()

class Loan(models.Model):
    loan_id = models.AutoField(primary_key=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    loan_amount = models.DecimalField(max_digits=10, decimal_places=2)
    tenure = models.IntegerField() # In months
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2) # Percentage (e.g., 8.50)
    monthly_installment = models.DecimalField(max_digits=10, decimal_places=2)
    emis_paid_on_time = models.IntegerField(default=0)
    date_of_approval = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    # Fields to store loan status and message (as per API response requirements)
    loan_approved = models.BooleanField(default=False)
    message = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"Loan {self.loan_id} for Customer {self.customer.customer_id}"

    @property
    def repayments_left(self):
        # Calculate remaining repayments based on total tenure and EMIs paid
        return self.tenure - self.emis_paid_on_time