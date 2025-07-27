# backend/core/management/commands/ingest_data.py

import pandas as pd
from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Customer, Loan
import os
from datetime import datetime

class Command(BaseCommand):
    help = 'Ingests customer_data.xlsx and loan_data.xlsx into the database.'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS('Starting data ingestion...'))

        # Define paths relative to the project root (where docker-compose.yml is)
        # This path is crucial for Docker to find the files
        PROJECT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '..')
        CUSTOMER_DATA_PATH = os.path.join(PROJECT_ROOT, 'customer_data.xlsx')
        LOAN_DATA_PATH = os.path.join(PROJECT_ROOT, 'loan_data.xlsx')


        self.stdout.write(f"Customer data path: {CUSTOMER_DATA_PATH}")
        self.stdout.write(f"Loan data path: {LOAN_DATA_PATH}")


        # --- Ingest Customer Data ---
        try:
            customer_df = pd.read_excel(CUSTOMER_DATA_PATH)
            self.stdout.write(self.style.SUCCESS(f"Loaded {len(customer_df)} rows from customer_data.xlsx"))
            # Rename columns to match model fields (case-insensitive and replace spaces)
            customer_df.columns = customer_df.columns.str.lower().str.replace(' ', '_')

            with transaction.atomic():
                # Clear existing customer data if re-running (useful for development)
                Customer.objects.all().delete()
                self.stdout.write(self.style.WARNING('Existing customer data cleared.'))

                customers_to_create = []
                for index, row in customer_df.iterrows():
                    approved_limit = row.get('approved_limit')
                    if approved_limit is None: # Calculate if not explicitly present or if it needs to be derived
                        approved_limit = row['monthly_salary'] * 36

                    customers_to_create.append(
                        Customer(
                            customer_id=row['customer_id'],
                            first_name=row['first_name'],
                            last_name=row['last_name'],
                            phone_number=row['phone_number'],
                            monthly_salary=row['monthly_salary'],
                            approved_limit=approved_limit,
                            current_debt=row.get('current_debt', 0)
                        )
                    )
                Customer.objects.bulk_create(customers_to_create, ignore_conflicts=True)
                self.stdout.write(self.style.SUCCESS(f'Successfully ingested {len(customers_to_create)} customer records.'))

        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"Error: customer_data.xlsx not found at {CUSTOMER_DATA_PATH}"))
            return
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error ingesting customer data: {e}"))
            return

        # --- Ingest Loan Data ---
        try:
            loan_df = pd.read_excel(LOAN_DATA_PATH)
            self.stdout.write(self.style.SUCCESS(f"Loaded {len(loan_df)} rows from loan_data.xlsx"))
            # Rename columns to match model fields
            loan_df.columns = loan_df.columns.str.lower().str.replace(' ', '_')
            loan_df.rename(columns={
                'monthly_payment': 'monthly_installment', # Rename for consistency with model
            }, inplace=True)

            with transaction.atomic():
                # Clear existing loan data if re-running
                Loan.objects.all().delete()
                self.stdout.write(self.style.WARNING('Existing loan data cleared.'))

                loans_to_create = []
                for index, row in loan_df.iterrows():
                    try:
                        # Ensure customer exists before linking loan
                        customer = Customer.objects.get(customer_id=row['customer_id'])

                        # Handle date parsing, ensuring None for NaT
                        date_of_approval = pd.to_datetime(row['date_of_approval']).date() if pd.notna(row['date_of_approval']) else None
                        end_date = pd.to_datetime(row['end_date']).date() if pd.notna(row['end_date']) else None

                        loans_to_create.append(
                            Loan(
                                customer=customer,
                                loan_id=row['loan_id'],
                                loan_amount=row['loan_amount'],
                                tenure=row['tenure'],
                                interest_rate=row['interest_rate'],
                                monthly_installment=row['monthly_installment'],
                                emis_paid_on_time=row['emis_paid_on_time'],
                                date_of_approval=date_of_approval,
                                end_date=end_date
                            )
                        )
                    except Customer.DoesNotExist:
                        self.stdout.write(self.style.WARNING(f"Skipping loan {row['loan_id']}: Customer {row['customer_id']} not found for loan ingestion."))
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"Error processing loan {row['loan_id']}: {e}"))

                Loan.objects.bulk_create(loans_to_create, ignore_conflicts=True)
                self.stdout.write(self.style.SUCCESS(f'Successfully ingested {len(loans_to_create)} loan records.'))

        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"Error: loan_data.xlsx not found at {LOAN_DATA_PATH}"))
            return
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error ingesting loan data: {e}"))
            return

        self.stdout.write(self.style.SUCCESS('Data ingestion complete!'))