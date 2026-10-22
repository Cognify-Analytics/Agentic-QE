---
title: Testing Spring Boot Applications
impact: HIGH
impactDescription: unit-tests Spring code without the cost and fragility of a full application context, and uses test slices only where they test something a plain unit test cannot
tags: java, kotlin, spring-boot, mockmvc, webmvctest, mockitobean, validation, spring-security
---

## Testing Spring Boot Applications

Read this when the build depends on `spring-boot-starter-*`. It applies to Java and Kotlin; Kotlin specifics are in §8.

### 1. Default: A Plain Unit Test, No Spring Context

Services, components, mappers, validators and domain classes are plain objects. Construct them directly, with Mockito/MockK fakes for their collaborators (`mocking-java.md`, `mocking-kotlin.md`). No `@SpringBootTest`, no `@Autowired`, no context startup:

```java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    private OrderRepository orderRepository;

    private final Clock clock = Clock.fixed(Instant.parse("2024-01-01T00:00:00Z"), ZoneOffset.UTC);

    private OrderService orderService;

    @BeforeEach
    void setUp() {
        orderService = new OrderService(orderRepository, clock);
    }
    // ...
}
```

This is the right test for the large majority of a Spring codebase. It runs in milliseconds and fails only for reasons inside the class.

- **Constructor injection** (the norm, including Lombok's `@RequiredArgsConstructor`): call the constructor.
- **Field injection** (`@Autowired` on fields): use `@InjectMocks` (`mocking-java.md` §2), and say in the notes that the class can only be tested that way.
- **`@Value` fields:** constructor-injected values are just arguments. For `@Value` on a field, `ReflectionTestUtils.setField(service, "maxItems", 10)` is the accepted last resort; note why it was needed.

### 2. When a Test Slice Earns Its Place

Use a slice only for behaviour that **lives in Spring configuration** and so can't be seen in a plain unit test:

| Target | Slice | What it tests that a unit test can't |
|---|---|---|
| `@RestController` / `@Controller` | `@WebMvcTest(OrderController.class)` + `MockMvc` | URL/method mapping, `@Valid` request validation, JSON (de)serialization, `@ControllerAdvice` error mapping, security rules |
| WebFlux controller | `@WebFluxTest(OrderController.class)` + `WebTestClient` | Same, reactive |
| DTO JSON shape (custom serializers, `@JsonProperty`, date formats) | `@JsonTest` + `JacksonTester<T>` | The exact JSON the API emits or accepts |
| Outgoing HTTP via `RestTemplate`/`RestClient` | `@RestClientTest` + `MockRestServiceServer` | Request built and response mapped, without a network |

**Never in v1:**

- **`@SpringBootTest`.** It loads the whole application, usually needs a database, a broker and environment config, and fails for reasons unrelated to the class under test. That makes it an integration test.
- **`@DataJpaTest` and other repository tests.** They need a real or embedded database. Derived query methods (`findByCustomerId`) are framework code, and custom `@Query` SQL needs a database to mean anything. Only follow an existing house pattern if the repo already runs `@DataJpaTest` against an embedded database successfully. Otherwise skip repositories with a `skipped_reason`.

### 3. Controllers with `@WebMvcTest`

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private OrderService orderService;

    @Test
    void createOrder_validRequest_returns201WithLocation() throws Exception {
        given(orderService.createOrder(any(CreateOrderRequest.class)))
                .willReturn(OrderTestData.anOrder().withId("ord-1").build());

        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"customerId": "cust-1", "items": [{"sku": "A-100", "quantity": 2}]}
                                """))
                .andExpect(status().isCreated())
                .andExpect(header().string("Location", "/orders/ord-1"))
                .andExpect(jsonPath("$.id").value("ord-1"));
    }

    @Test
    void createOrder_emptyItems_returns400AndNeverCallsService() throws Exception {
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"customerId": "cust-1", "items": []}
                                """))
                .andExpect(status().isBadRequest());

        then(orderService).shouldHaveNoInteractions();
    }
}
```

- **Every bean the controller injects must be provided** as a `@MockitoBean`. `@WebMvcTest` loads web-layer beans only (controllers, `@ControllerAdvice`, filters, converters, `WebMvcConfigurer`), not `@Service`/`@Repository`/`@Component`. A missing one fails context startup with `NoSuchBeanDefinitionException`.
- **`@MockitoBean` vs `@MockBean`:** Spring Boot 3.4+ uses `@MockitoBean` (`org.springframework.test.context.bean.override.mockito`). `@MockBean` is deprecated there and removed in Boot 4. Read the Boot version from the parent POM, plugin or BOM, and match existing tests.
- **Request bodies are JSON literals**, not `objectMapper.writeValueAsString(request)`. Serialising your own DTO makes the test agree with whatever the serializer does (`json-serialization.md`). Text blocks need Java 15+; below that, use a concatenated string.
- **Cover per endpoint:** success (status, `Location`/headers, body fields that matter), each validation failure (400, and the service never called), not-found (404 via the `@ControllerAdvice`), and how a domain exception from the service is mapped.
- **Spring Security** is active in `@WebMvcTest` when it's on the classpath, so requests without credentials get 401/403. Authenticate explicitly with `@WithMockUser(roles = "ADMIN")` or `.with(user("jane").roles("USER"))`, and add `.with(csrf())` for state-changing requests when CSRF is enabled (`spring-security-test` is needed for both). Write an **unauthenticated → 401** and a **wrong role → 403** test for protected endpoints; that's real behaviour worth pinning. Provide any beans the security config needs (a `JwtDecoder`, say) as `@MockitoBean`s. Don't disable filters (`addFilters = false`) unless the house style already does.

### 4. Bean Validation Without a Context

Constraint annotations on a DTO can be tested directly. It's faster than MockMvc, and gives better failure messages for many constraints:

```java
class CreateOrderRequestTest {

    private final Validator validator = Validation.buildDefaultValidatorFactory().getValidator();

    @Test
    void validate_emptyItems_reportsItemsViolation() {
        CreateOrderRequest request = new CreateOrderRequest("cust-1", List.of());

        Set<ConstraintViolation<CreateOrderRequest>> actualViolations = validator.validate(request);

        assertThat(actualViolations)
                .extracting(violation -> violation.getPropertyPath().toString())
                .containsExactly("items");
    }
}
```

Spring Boot 3 uses `jakarta.validation`; Boot 2 uses `javax.validation`. Copy the import from the DTO.

### 5. What Proxies Do Is Not Unit-Testable

`@Transactional`, `@Async`, `@Cacheable`, `@Retryable`, `@Scheduled` and `@PreAuthorize` on services work through Spring proxies that don't exist in a plain unit test. Test the method's own logic. Don't write a unit test that claims to verify a rollback, a cache hit or an authorisation check on a service method; it can't. Note it as a known gap instead.

### 6. Time, Config and Outgoing HTTP

- **Time:** if the class takes a `Clock` (or `Supplier<Instant>`), pass `Clock.fixed(...)`. If it calls `LocalDateTime.now()` directly, assert on what doesn't depend on the exact instant, or use `mockStatic` as a last resort (`mocking-java.md` §6). Never assert "within one second of now".
- **`@ConfigurationProperties`:** construct the properties object (records or setters) with test values. Don't load YAML.
- **Outgoing HTTP:** for a class that wraps `RestTemplate`/`RestClient`, use `@RestClientTest` + `MockRestServiceServer`. For `WebClient`, use `MockWebServer` (okhttp) if it's installed. Otherwise mock the wrapper class one level up. Never call a real URL.

### 7. Messaging and Scheduled Jobs

`@KafkaListener`, `@RabbitListener` and `@Scheduled` methods are plain methods. Call them directly with a constructed message or payload and assert the effect. Don't start a broker or wait for the scheduler.

### 8. Kotlin and Spring

- Constructor injection is idiomatic (`class OrderService(private val orders: OrderRepository, private val clock: Clock)`). Construct it directly with MockK fakes.
- In slices, use `@MockkBean` (from `com.ninja-squad:springmockk`) if it's installed. Otherwise use `@MockitoBean` with `mockito-kotlin`'s `whenever`.
- MockMvc has a Kotlin DSL; use it when existing tests do:

```kotlin
mockMvc.post("/orders") {
    contentType = MediaType.APPLICATION_JSON
    content = """{"customerId": "cust-1", "items": []}"""
}.andExpect {
    status { isBadRequest() }
}
```

- `spring-boot-starter-test` + Kotlin needs `jackson-module-kotlin` to bind JSON to data classes. If request binding fails with "no Creators" errors in a slice, that's a classpath gap. Report it; don't work around it.

### Checklist

- [ ] Services, components and domain classes tested without a Spring context, by calling the constructor
- [ ] Slices only for controller mapping/validation/error handling/security, JSON shape, or outgoing HTTP
- [ ] No `@SpringBootTest`; no repository tests unless the repo already runs them against an embedded DB
- [ ] Every injected collaborator in a slice is a `@MockitoBean`/`@MockBean`/`@MockkBean`, matching the Boot version
- [ ] Request bodies are JSON literals; success, validation, not-found, error-mapping and auth (401/403) paths covered
- [ ] No unit test claims to verify proxy behaviour (`@Transactional`, `@Cacheable`, `@Async`, `@PreAuthorize`)
