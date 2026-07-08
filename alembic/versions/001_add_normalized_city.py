"""add normalized_city field

Revision ID: 001_add_normalized_city
Revises: 
Create Date: 2026-07-08

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001_add_normalized_city'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Добавляем колонку normalized_city с nullable=True для совместимости
    op.add_column('users', sa.Column('normalized_city', sa.String(50), nullable=True))
    
    # Создаем индекс на normalized_city
    op.create_index('ix_users_normalized_city', 'users', ['normalized_city'])


def downgrade() -> None:
    # Удаляем индекс
    op.drop_index('ix_users_normalized_city', 'users')
    
    # Удаляем колонку
    op.drop_column('users', 'normalized_city')
