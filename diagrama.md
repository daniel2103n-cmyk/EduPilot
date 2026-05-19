# Diagrama de Clases — EduPilot

A continuación se muestra el diagrama de clases del sistema con sus respectivos campos, tipos de relaciones y métodos principales de validación de negocio.

```mermaid
classDiagram
    direction TB
    
    class User {
        +role : CharField (ADMIN, STUDENT)
        +username : CharField
        +email : EmailField
        +first_name : CharField
        +last_name : CharField
    }
    
    class StudentProfile {
        +user : OneToOneField
        +program : ForeignKey
        +current_semester : IntegerField
    }
    
    class AcademicProgram {
        +name : CharField
        +is_active : BooleanField
    }
    
    class Course {
        +name : CharField
        +code : CharField
        +description : TextField
        +credits : IntegerField (0-10)
        +level : IntegerField
        +program : ForeignKey
        +color : CharField
        +is_active : BooleanField
    }
    
    class Prerequisite {
        +course : ForeignKey
        +required_course : ForeignKey
        +clean()
    }
    
    class AcademicRecord {
        +student : ForeignKey
        +course : ForeignKey
        +status : CharField (PASSED, FAILED, IN_PROGRESS)
        +grade : FloatField (0.0-5.0)
        +semester_taken : IntegerField
        +clean()
        +save()
    }

    User "1" -- "1" StudentProfile : OneToOneField
    StudentProfile "*" --> "0..1" AcademicProgram : program
    Course "*" --> "0..1" AcademicProgram : program
    Prerequisite "*" --> "1" Course : course
    Prerequisite "*" --> "1" Course : required_course
    AcademicRecord "*" --> "1" StudentProfile : student
    AcademicRecord "*" --> "1" Course : course
```

## Resumen de Relaciones y Reglas de Negocio Representadas

1. **`User` a `StudentProfile` (1:1):** Cada usuario con rol de estudiante tiene un perfil único que contiene su información académica.
2. **`AcademicProgram` (1:N):**
   * Un programa académico puede tener múltiples estudiantes matriculados (`StudentProfile`).
   * Un programa académico tiene un conjunto de materias (`Course`) que conforman su plan de estudios.
3. **`Course` y `Prerequisite` (Autorelación N:M):**
   * La clase intermedia `Prerequisite` relaciona una materia (`course`) con otra materia requerida (`required_course`).
   * **Validación de Ciclos (DFS):** El método `clean()` de `Prerequisite` ejecuta una búsqueda en profundidad para impedir ciclos de prerrequisitos (ej. que A requiera B, y B requiera A).
4. **`AcademicRecord` (Historial Académico):**
   * Relaciona a un `StudentProfile` con un `Course` para registrar notas, semestres de cursada y estados.
   * **Validación de Límites:** El método `clean()` asegura que la nota final esté entre `0.0` y `5.0`. También valida que un estudiante no intente cursar/reprobar una materia más de **3 veces**, activando la alerta de pérdida de calidad de estudiante en la plataforma.