# backend/core/utils.py

import math
from datetime import date, timedelta
from decimal import Decimal

def calculate_emi(loan_amount, annual_interest_rate, tenure_months):
    """
    Calculates EMI using the compound interest formula.
    EMI = P * R * (1 + R)^N / ((1 + R)^N – 1)
    Where:
    P = Principal Loan Amount
    R = Monthly Interest Rate (annual_interest_rate / 12 / 100)
    N = Number of Monthly Installments (tenure_months)
    """
    if annual_interest_rate == 0:
        return loan_amount / tenure_months

    # Convert annual interest rate to monthly decimal rate
    monthly_interest_rate = (annual_interest_rate / 100) / 12

    # Calculate EMI
    # Use Decimal for financial calculations to avoid floating point inaccuracies
    try:
        emi = (
            loan_amount * monthly_interest_rate * (1 + monthly_interest_rate)**tenure_months
        ) / ((1 + monthly_interest_rate)**tenure_months - 1)
    except ZeroDivisionError: # Handle case where denominator becomes zero (e.g. 0% interest for 1 month)
        return loan_amount / tenure_months


    return Decimal(emi).quantize(Decimal('0.01')) # Round to 2 decimal places

def check_credit_eligibility(customer, loan_amount, annual_interest_rate, tenure):
    """
    Calculates credit eligibility and revised interest rate.
    Returns:
        tuple: (approved_status_boolean, interest_rate_if_approved, monthly_installment_if_approved, tenure, approval_message)
    """
    customer_id = customer.customer_id
    current_debt = customer.current_debt
    approved_limit = customer.approved_limit
    monthly_salary = customer.monthly_salary

    # Get past loans for the customer
    from core.models import Loan # Import here to avoid circular dependency
    past_loans = Loan.objects.filter(customer=customer)

    # Rule 1: Check if sum of all current loans + requested loan amount > approved limit
    # 'current_debt' from customer data is aggregate of past active loans.
    # We need to consider actual active loans from DB as well to be robust.
    # For simplicity, let's use the 'current_debt' provided in customer data, plus active loans.
    # Assuming current_debt in customer_data already reflects all *existing* active loans.
    # The new loan will add to it if approved.

    # Calculate EMI for requested loan, assuming requested interest rate initially
    requested_monthly_installment = calculate_emi(loan_amount, annual_interest_rate, tenure)

    # Rule for sum of current EMIs of all active loans + requested loan EMI > 50% of monthly salary
    # This implies we need to sum EMIs of *active* loans. The assignment's 'current_debt' is amount.
    # If 'current_debt' is the sum of outstanding loan amounts, not EMIs, then this rule needs active loan EMIs from DB.
    # Let's assume current_debt in customer is the outstanding principal.

    # We need total monthly EMI of existing active loans. The provided loan_data doesn't distinguish 'active'.
    # Assuming 'current_debt' on customer model is the total outstanding principal across all active loans.
    # To apply the 50% rule, we need the sum of *monthly_installments* of all *active* loans.
    # Since 'loan_data.xlsx' doesn't distinguish active, we'll sum all past loan's monthly_installments.
    total_existing_monthly_emis = sum(loan.monthly_installment for loan in past_loans)

    if (total_existing_monthly_emis + requested_monthly_installment) > (monthly_salary * Decimal('0.50')):
        return False, None, None, None, "Loan not approved: Total monthly EMI exceeds 50% of monthly salary."

    # Credit Score Logic based on past loans paid on time
    # Higher score for better repayment history.
    credit_score = 0
    if past_loans.exists():
        total_loans_taken = past_loans.count()
        loans_paid_on_time = past_loans.filter(emis_paid_on_time__gte=models.F('tenure')).count() # Simplified: EMIs paid >= Tenure means paid on time

        # Additional metric: Number of loans with no EMIs missed (i.e., emis_paid_on_time == tenure)
        fully_paid_loans = past_loans.filter(emis_paid_on_time=models.F('tenure')).count()

        # Simple credit score based on ratio of loans fully paid on time
        if total_loans_taken > 0:
            credit_score = (fully_paid_loans / total_loans_taken) * 100
        else:
            credit_score = 100 # No past loans, perfect score

    else: # No past loans
        credit_score = 100 # Perfect credit score if no history

    final_interest_rate = annual_interest_rate

    if credit_score < 30:
        return False, None, None, None, "Loan not approved: Credit score too low (below 30)."
    elif credit_score >= 30 and credit_score < 50:
        final_interest_rate = Decimal('12.00')
    elif credit_score >= 50 and credit_score < 70:
        final_interest_rate = Decimal('10.00')
    else: # credit_score >= 70
        final_interest_rate = Decimal('8.00')

    # Ensure that the final interest rate is not lower than the requested interest rate
    final_interest_rate = max(final_interest_rate, annual_interest_rate)

    # Re-calculate monthly installment with the final_interest_rate
    monthly_installment = calculate_emi(loan_amount, final_interest_rate, tenure)

    # Rule: If sum of current debt + requested loan amount exceeds approved_limit
    if (customer.current_debt + loan_amount) > customer.approved_limit:
        return False, None, None, None, "Loan not approved: Total debt including new loan exceeds approved limit."


    return True, final_interest_rate, monthly_installment, tenure, "Loan approved."