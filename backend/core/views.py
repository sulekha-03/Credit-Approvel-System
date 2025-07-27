# backend/core/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth import authenticate
from django.db.models import Sum, F
from datetime import date, timedelta
from decimal import Decimal
import math

from .models import Customer, Loan
from .serializers import (
    RegisterCustomerSerializer, LoanApplicationSerializer,
    LoanDetailSerializer, CustomerLoansListSerializer
)

# Helper function for EMI calculation (Compound Interest)
def calculate_emi(loan_amount, annual_interest_rate, tenure_months):
    if annual_interest_rate == 0 or tenure_months == 0:
        return Decimal('0.00') # Or handle as error/special case

    # Convert annual interest rate to monthly decimal rate
    monthly_interest_rate = annual_interest_rate / 12 / 100

    if monthly_interest_rate == 0: # For 0% interest
        emi = loan_amount / tenure_months
    else:
        # Formula for EMI: P * R * (1 + R)^N / ((1 + R)^N - 1)
        # Where P = Principal, R = Monthly Interest Rate, N = Tenure in Months
        numerator = loan_amount * monthly_interest_rate * (1 + monthly_interest_rate)**tenure_months
        denominator = ((1 + monthly_interest_rate)**tenure_months - 1)
        if denominator == 0: # Should not happen with positive interest rates and tenure
            return Decimal('0.00')
        emi = numerator / denominator

    return Decimal(emi).quantize(Decimal('0.01')) # Round to 2 decimal places

class RegisterView(APIView):
    permission_classes = [AllowAny] # Allow anyone to register

    def post(self, request):
        serializer = RegisterCustomerSerializer(data=request.data)
        if serializer.is_valid():
            customer = serializer.save()
            return Response({
                'customer_id': customer.customer_id,
                'message': 'Customer registered successfully'
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LoginView(APIView):
    permission_classes = [AllowAny] # Allow anyone to login

    def post(self, request):
        username = request.data.get('username') # Assuming phone_number is used as username
        password = request.data.get('password')

        user = authenticate(username=username, password=password)
        if user:
            token, created = Token.objects.get_or_create(user=user)
            return Response({'customer_id': user.customer.customer_id, 'token': token.key}, status=status.HTTP_200_OK)
        return Response({'message': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

class CheckEligibilityView(APIView):
    permission_classes = [IsAuthenticated] # Requires authentication

    def post(self, request):
        serializer = LoanApplicationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        customer_id = serializer.validated_data['customer_id']
        loan_amount = serializer.validated_data['loan_amount']
        tenure = serializer.validated_data['tenure']
        interest_rate = serializer.validated_data['interest_rate']

        try:
            customer = Customer.objects.get(customer_id=customer_id)
        except Customer.DoesNotExist:
            return Response({'message': 'Customer not found'}, status=status.HTTP_404_NOT_FOUND)

        # Ensure authenticated user matches the requested customer_id
        if request.user.customer != customer:
            return Response({'message': 'Unauthorized access to customer data'}, status=status.HTTP_403_FORBIDDEN)

        # --- Business Logic for Eligibility ---

        # 1. Check sum of all current EMIs of existing active loans > 50% of monthly salary
        # "Active" loans: approved loans whose end_date is in the future or today
        active_loans = customer.loan_set.filter(loan_approved=True, end_date__gte=date.today())
        total_current_emis = active_loans.aggregate(Sum('monthly_installment'))['monthly_installment__sum'] or Decimal('0.00')

        proposed_emi = calculate_emi(loan_amount, interest_rate, tenure)

        if (total_current_emis + proposed_emi) > (customer.monthly_salary * Decimal('0.5')):
            return Response({
                "customer_id": customer.customer_id,
                "loan_approved": False,
                "approved_limit": customer.approved_limit,
                "interest_rate": interest_rate, # Original requested rate
                "monthly_installment": proposed_emi,
                "tenure": tenure,
                "message": "Loan rejected: Total EMIs (including proposed) exceed 50% of monthly salary"
            }, status=status.HTTP_200_OK)

        # 2. Past loan repayment history (EMIs paid on time rate)
        past_loans_count = customer.loan_set.count()
        final_interest_rate = interest_rate # Start with requested rate

        if past_loans_count > 0:
            # Sum of EMIs paid on time vs. total expected EMIs across all past loans
            total_emis_paid_on_time = customer.loan_set.aggregate(Sum('emis_paid_on_time'))['emis_paid_on_time__sum'] or 0
            total_tenure_sum = customer.loan_set.aggregate(Sum('tenure'))['tenure__sum'] or 1 # Avoid division by zero

            # Simple "credit score" based on EMIs paid on time ratio
            credit_score_percentage = (total_emis_paid_on_time / total_tenure_sum) * 100

            if credit_score_percentage > 85: # Excellent repayment
                final_interest_rate = interest_rate # Keep requested rate
            elif 85 >= credit_score_percentage > 60: # Good repayment
                final_interest_rate = max(interest_rate, Decimal('12.00')) # At least 12%
            elif 60 >= credit_score_percentage > 40: # Moderate repayment
                final_interest_rate = max(interest_rate, Decimal('16.00')) # At least 16%
            else: # Poor repayment history
                return Response({
                    "customer_id": customer.customer_id,
                    "loan_approved": False,
                    "approved_limit": customer.approved_limit,
                    "interest_rate": interest_rate,
                    "monthly_installment": proposed_emi,
                    "tenure": tenure,
                    "message": "Loan rejected: Poor past loan repayment history (less than 40% EMIs on time)"
                }, status=status.HTTP_200_OK)
        else:
            # New customer with no past loans, consider it good for interest rate
            # The assignment doesn't specify a special rate for new customers, so use requested.
            # If you want to enforce a minimum for new customers, e.g., 10%, add:
            # final_interest_rate = max(interest_rate, Decimal('10.00'))
            pass


        # 3. Check if current_debt + requested loan_amount > approved_limit
        # customer.current_debt should reflect the total outstanding principal from active loans.
        # Assuming current_debt is updated correctly by the system.
        if (customer.current_debt + loan_amount) > customer.approved_limit:
            return Response({
                "customer_id": customer.customer_id,
                "loan_approved": False,
                "approved_limit": customer.approved_limit,
                "interest_rate": interest_rate,
                "monthly_installment": proposed_emi,
                "tenure": tenure,
                "message": "Loan rejected: Proposed loan amount plus current debt exceeds approved limit"
            }, status=status.HTTP_200_OK)

        # All checks passed, loan is eligible
        final_monthly_installment = calculate_emi(loan_amount, final_interest_rate, tenure)

        return Response({
            "customer_id": customer.customer_id,
            "loan_approved": True,
            "approved_limit": customer.approved_limit,
            "interest_rate": final_interest_rate,
            "monthly_installment": final_monthly_installment,
            "tenure": tenure,
            "message": "Loan is eligible for approval"
        }, status=status.HTTP_200_OK)

class CreateLoanView(APIView):
    permission_classes = [IsAuthenticated] # Requires authentication

    def post(self, request):
        serializer = LoanApplicationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        customer_id = serializer.validated_data['customer_id']
        loan_amount = serializer.validated_data['loan_amount']
        tenure = serializer.validated_data['tenure']
        interest_rate = serializer.validated_data['interest_rate']

        try:
            customer = Customer.objects.get(customer_id=customer_id)
        except Customer.DoesNotExist:
            return Response({'message': 'Customer not found'}, status=status.HTTP_404_NOT_FOUND)

        # Ensure authenticated user matches the requested customer_id
        if request.user.customer != customer:
            return Response({'message': 'Unauthorized access'}, status=status.HTTP_403_FORBIDDEN)

        # Re-run eligibility checks to determine final approval and terms
        # This is critical to ensure consistency with eligibility check
        approved, final_interest_rate, monthly_installment, final_tenure, message = self._run_eligibility_checks(
            customer, loan_amount, tenure, interest_rate
        )

        if not approved:
            return Response({
                'loan_id': None,
                'customer_id': customer_id,
                'loan_approved': False,
                'message': message,
                'monthly_installment': None # No installment if not approved
            }, status=status.HTTP_200_OK) # Return 200 OK with approval status false

        with transaction.atomic():
            # Create the new loan record
            new_loan = Loan.objects.create(
                customer=customer,
                loan_amount=loan_amount,
                tenure=final_tenure,
                interest_rate=final_interest_rate,
                monthly_installment=monthly_installment,
                emis_paid_on_time=0, # New loan starts with 0 EMIs paid
                date_of_approval=date.today(),
                end_date=date.today() + timedelta(days=30 * final_tenure), # Approximate end date
                loan_approved=True,
                message="Loan approved and created"
            )

            # Update customer's current_debt
            # This should add the principal of the new loan to current_debt
            customer.current_debt += loan_amount
            customer.save()

        response_data = {
            "loan_id": new_loan.loan_id,
            "customer_id": customer.customer_id,
            "loan_approved": True,
            "message": "Loan approved and created successfully.",
            "monthly_installment": new_loan.monthly_installment,
        }
        return Response(response_data, status=status.HTTP_201_CREATED)

    def _run_eligibility_checks(self, customer, loan_amount, tenure, interest_rate):
        # This internal method encapsulates the eligibility logic for re-use
        # It's a simplified copy from CheckEligibilityView for direct use here.

        # 1. Check sum of all current EMIs of existing active loans > 50% of monthly salary
        active_loans = customer.loan_set.filter(loan_approved=True, end_date__gte=date.today())
        total_current_emis = active_loans.aggregate(Sum('monthly_installment'))['monthly_installment__sum'] or Decimal('0.00')
        proposed_emi = calculate_emi(loan_amount, interest_rate, tenure)

        if (total_current_emis + proposed_emi) > (customer.monthly_salary * Decimal('0.5')):
            return False, None, None, None, "Loan rejected: Total EMIs (including proposed) exceed 50% of monthly salary"

        # 2. Past loan repayment history (EMIs paid on time rate)
        past_loans_count = customer.loan_set.count()
        final_interest_rate = interest_rate

        if past_loans_count > 0:
            total_emis_paid_on_time = customer.loan_set.aggregate(Sum('emis_paid_on_time'))['emis_paid_on_time__sum'] or 0
            total_tenure_sum = customer.loan_set.aggregate(Sum('tenure'))['tenure__sum'] or 1
            credit_score_percentage = (total_emis_paid_on_time / total_tenure_sum) * 100

            if credit_score_percentage > 85:
                final_interest_rate = interest_rate
            elif 85 >= credit_score_percentage > 60:
                final_interest_rate = max(interest_rate, Decimal('12.00'))
            elif 60 >= credit_score_percentage > 40:
                final_interest_rate = max(interest_rate, Decimal('16.00'))
            else:
                return False, None, None, None, "Loan rejected: Poor past loan repayment history (less than 40% EMIs on time)"
        else:
            pass # New customer, no special rate adjustment based on history

        # 3. Check if current_debt + requested loan_amount > approved_limit
        if (customer.current_debt + loan_amount) > customer.approved_limit:
            return False, None, None, None, "Loan rejected: Proposed loan amount plus current debt exceeds approved limit"

        # All checks passed
        final_monthly_installment = calculate_emi(loan_amount, final_interest_rate, tenure)
        return True, final_interest_rate, final_monthly_installment, tenure, "Loan approved"


class ViewLoanDetailsView(APIView):
    permission_classes = [IsAuthenticated] # Requires authentication

    def get(self, request, loan_id):
        try:
            loan = Loan.objects.get(loan_id=loan_id)
        except Loan.DoesNotExist:
            return Response({'message': 'Loan not found'}, status=status.HTTP_404_NOT_FOUND)

        # Ensure authenticated user owns this loan's customer
        if request.user.customer != loan.customer:
            return Response({'message': 'Unauthorized access to loan details'}, status=status.HTTP_403_FORBIDDEN)

        serializer = LoanDetailSerializer(loan)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ViewCustomerLoansView(APIView):
    permission_classes = [IsAuthenticated] # Requires authentication

    def get(self, request, customer_id):
        try:
            customer = Customer.objects.get(customer_id=customer_id)
        except Customer.DoesNotExist:
            return Response({'message': 'Customer not found'}, status=status.HTTP_404_NOT_FOUND)

        # Ensure authenticated user matches the requested customer_id
        if request.user.customer != customer:
            return Response({'message': 'Unauthorized access to customer loans'}, status=status.HTTP_403_FORBIDDEN)

        # Filter for current/active loans: approved loans where repayments_left > 0
        # or end_date is in the future/today.
        # The assignment asks for "all current loan details".
        # Let's interpret "current" as approved loans that are not yet fully paid.
        current_loans = customer.loan_set.filter(
            loan_approved=True,
            repayments_left__gt=0 # Using the property from the model
        ).order_by('-date_of_approval') # Order by most recent first

        serializer = CustomerLoansListSerializer(current_loans, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)