# backend/core/urls.py
from django.urls import path
from .views import (
    RegisterView, LoginView, CheckEligibilityView, CreateLoanView,
    ViewLoanDetailsView, ViewCustomerLoansView
)

urlpatterns = [
    path('register', RegisterView.as_view(), name='register'),
    path('login', LoginView.as_view(), name='login'),
    path('check_eligibility', CheckEligibilityView.as_view(), name='check_eligibility'),
    path('create_loan', CreateLoanView.as_view(), name='create_loan'),
    path('view-loan/<int:loan_id>', ViewLoanDetailsView.as_view(), name='view_loan_details'),
    path('view-loans/<int:customer_id>', ViewCustomerLoansView.as_view(), name='view_customer_loans'),
]