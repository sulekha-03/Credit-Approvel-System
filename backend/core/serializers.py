# backend/core/serializers.py
from rest_framework import serializers
from .models import Customer, Loan
from django.contrib.auth.models import User

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['username', 'password'] # Only for registration/creation
        extra_kwargs = {'password': {'write_only': True}} # Password is write-only

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            password=validated_data['password']
        )
        return user

class CustomerDetailSerializer(serializers.ModelSerializer):
    # This serializer is for displaying customer details in the /view-loan endpoint
    class Meta:
        model = Customer
        fields = [
            'customer_id', 'first_name', 'last_name', 'phone_number', 'age'
        ]

class LoanDetailSerializer(serializers.ModelSerializer):
    customer = CustomerDetailSerializer(read_only=True) # Nested serializer for customer details

    class Meta:
        model = Loan
        fields = [
            'loan_id', 'customer', 'loan_amount', 'tenure',
            'interest_rate', 'monthly_installment', 'emis_paid_on_time',
            'date_of_approval', 'end_date', 'loan_approved', 'message',
            'repayments_left'
        ]

class RegisterCustomerSerializer(serializers.ModelSerializer):
    # This serializer is specifically for the /register endpoint
    password = serializers.CharField(write_only=True) # Field for password input

    class Meta:
        model = Customer
        fields = [
            'customer_id', 'first_name', 'last_name', 'age',
            'phone_number', 'monthly_salary',
            'password' # Include password for user creation
        ]
        read_only_fields = ['customer_id', 'approved_limit', 'current_debt'] # Auto-generated/calculated

    def create(self, validated_data):
        # Create Django User linked to the customer
        user = User.objects.create_user(
            username=validated_data['phone_number'], # Using phone number as username for login
            password=validated_data.pop('password') # Remove password from customer data
        )

        # Calculate approved_limit based on monthly_salary * 36
        monthly_salary = validated_data['monthly_salary']
        validated_data['approved_limit'] = monthly_salary * 36

        # Create Customer and link to User
        customer = Customer.objects.create(user=user, **validated_data)
        return customer

class LoanApplicationSerializer(serializers.Serializer):
    # This serializer is for /check_eligibility and /create_loan request bodies
    customer_id = serializers.IntegerField()
    loan_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    tenure = serializers.IntegerField()
    interest_rate = serializers.DecimalField(max_digits=5, decimal_places=2)

class CustomerLoansListSerializer(serializers.ModelSerializer):
    # This serializer is for the /view-loans/<customer_id> endpoint
    repayments_left = serializers.SerializerMethodField()

    class Meta:
        model = Loan
        fields = [
            'loan_id', 'loan_amount', 'interest_rate',
            'monthly_installment', 'repayments_left'
        ]

    def get_repayments_left(self, obj):
        return obj.repayments_left # Uses the @property from the model